#!/usr/bin/python
# Copyright 2015 Chris Spalding (c_spalding@hotmail.com) - free for noncommercial use.
# version 0.0.1 - 1 November 2015
# Prototyped in Python 2.7.10 in Darwin on OS X 10.10.5

'''This is a quick and dirty utility to upload the csv preaching roster to 
WordPress with interactive prompting.  The first argument is the xmlrpc url and
 the second one is the csv file
 
 Requires wordpress_xmlrpc and pytz, tzlocal
 '''

import os
import sys
import csv
from getpass import getpass
from datetime import datetime, time
import pytz
from tzlocal import get_localzone

from wordpress_xmlrpc import Client, WordPressPost, WordPressTerm
from wordpress_xmlrpc.methods.posts import GetPosts, EditPost, NewPost, DeletePost
from wordpress_xmlrpc.methods.taxonomies import GetTerms, NewTerm, GetTaxonomy, GetTerm
from wordpress_xmlrpc.methods.options import GetOptions

def getdatetime(datestring, default = None):
    returndate = None
    counter = 0
    dateformats = {0: '%d/%m/%Y', 1: '%b-%d %Y', 2: '%Y-%m-%d', 3: '%d-%m-%Y'}
    while returndate == None and counter in dateformats:
        try:
            returndate = datetime.strptime(datestring, dateformats[counter])
        except ValueError:
            returndate = None
        counter += 1
        if not (counter in dateformats) and returndate == None:
            print('"' + datestring + '"')
            userdate = raw_input('What format is the date? I can\'t work it out.\n%b = mmm, %B = mmmm, %d = dd, %m = mm (decimal), %y = yy, %Y = YYYY\n')
            if not userdate:
                break
            dateformats[counter] = userdate
    if returndate == None:
        return default
    else:
        return returndate
        
def gettime(datestring, default = None):
    returndate = None
    counter = 0
    dateformats = {0: '%H:%M', 1: '%I:%M %p', 2: '%I:%M%p'}
    while returndate == None and counter in dateformats:
        try:
            returndate = datetime.strptime(datestring, dateformats[counter])
        except:
            returndate = None
        counter += 1
        if not (counter in dateformats) and returndate == None:
            print('"' + datestring + '"')
            userdate = raw_input('What format is the time? I can\'t work it out.\n%H = hour of 24, %I = hour of 12, %M = mins, %p = am/pm\n')
            if not userdate:
                break
            dateformats[counter] = userdate
    if returndate == None:
        return default
    else:
        return returndate      
          
def cleanUpScripture(scriptureref):
    return scriptureref.replace('.', ':').replace(';', ',')

def main():
    args = sys.argv [1:]
    if len(args) != 2:
        print('Usage: ./ssp_se_load_roster.py <Wordpress xmlrpc url> <csvfile>')
        sys.exit(1)
    
    xmlrpc = args[0]
    csvfile_name = args[1]
    
    if not os.path.isfile(csvfile_name):
        print('I can\'t find the file: ' + csvfile_name)
        sys.exit(1)
        
    username = raw_input('Enter your WordPress user name: ')
    password = getpass()    

    wp = Client(xmlrpc, username, password)
    
    listofseriesterms = wp.call(GetTerms('series'))
    
    print('To which series are you going to add all these posts? (id, name)')
    series = {}
    for seriesterm in listofseriesterms:
        print(seriesterm.id + ', ' + seriesterm.name)
        series[seriesterm.id] = seriesterm.name
    main_series_termid = raw_input('Please enter the id: ')
    
    if not main_series_termid in series:
        print('That series id does not exist')
        sys.exit(1)
    else:
        print(series[main_series_termid] + ' series selected.')
        
    child_series = {}
    for seriesterm in listofseriesterms:
        if seriesterm.parent == main_series_termid:
            child_series[seriesterm.name.lower()] = seriesterm.id
    
    print('child_series')        
    print(child_series)
            
    existing_posts = wp.call(GetPosts({'post_type': 'podcast', 'number': 9999}))
    existing_series_posts = {}
    child_series_existing_episode_numbers = {}
    for post in existing_posts:
        post_terms = []
        for term in post.terms:
            if term.id in child_series.values() or term.id == main_series_termid:
                post_terms.append(term.id)
        if post_terms:
            for customfield in post.custom_fields:
                if customfield['key'] == 'date_recorded' and customfield['value']:
                    date_recorded_string = customfield['value']
                elif customfield['key'] == 'episode_number' and customfield['value']:
                    for post_term_id in post_terms:
                        if post_term_id in child_series_existing_episode_numbers:
                            child_series_existing_episode_numbers[post_term_id].append(int(customfield['value']))
                        else:
                            child_series_existing_episode_numbers[post_term_id] = [int(customfield['value'])]
            date_recorded = getdatetime(date_recorded_string)
            existing_series_posts[date_recorded] = (post.id, post_terms)
            
    #open and parse the csv
    replace_all = False
    replace_none = False
    
    fieldname_translation = {'date': 'date_recorded',
                             'title': 'title',
                             'series': 'series',
                             'track': 'episode_number',
                             'passage': 'bible_passage',
                             'preacher': 'preacher',
                             'comments' : 'content',
                             'time' : 'time'
                            }
    
    list_from_csv = {}
    with open(csvfile_name, 'r') as csvfile:
        reader = csv.DictReader(csvfile)
        for messyentry in reader:
            entry = {}
            for entrykey, entryval in messyentry.iteritems():
                entry[fieldname_translation[entrykey.lower()]] = entryval
            if not (('date_recorded' in entry) or ('preacher' in entry)):
                continue
            if entry['date_recorded'] == '' or entry['preacher'] == '':
                continue
            csvdate = getdatetime(entry['date_recorded'])
            if csvdate == None:
                continue
            entry['date_recorded'] = csvdate.strftime('%d-%m-%Y')
            try:
                int(entry['episode_number'])
            except (ValueError, KeyError): 
                entry['episode_number'] = ''
            for fieldname in fieldname_translation.values():
                if not fieldname in entry:
                    entry[fieldname] = ''
            if not entry['series']:
                entry['series'] = 'one-off'
            if (csvdate in existing_series_posts):
                if not (replace_none or replace_all):
                    confirmation_raw_in = raw_input('There is already a podcast in this series with date ' + csvdate.strftime('%d %b %Y') + ', replace it? \n(Y/N/All/None)\n').lower()
                elif replace_none:
                    continue
                if confirmation_raw_in == 'none':
                    replace_none = True
                if not confirmation_raw_in in ['y', 'all']:
                    continue
                if confirmation_raw_in == 'all':
                    replace_all = True
                if wp.call(DeletePost(existing_series_posts[csvdate][0])):
                    print('Deleted old post for ' + csvdate.strftime('%d %b %Y') + '.')
            entry['bible_passage'] = cleanUpScripture(entry['bible_passage'])
            list_from_csv[csvdate] = entry
   
    template_settings = {'ep_title_template': 'title',
        'service_time' : 'time',
        'comments_template': 'content'
        }
        
    #work out series and episode_numbers:
    for seriestermid in child_series_existing_episode_numbers:
        try:
            child_series_existing_episode_numbers[seriestermid] = sorted(child_series_existing_episode_numbers[seriestermid], reverse = True)[0]
        except IndexError as e:
            print(e)
            try:
                child_series_existing_episode_numbers[seriestermid] = int(series[seriestermid].count)
            except:
                child_series_existing_episode_numbers[seriestermid] = 0

    prefix = 'ss_podcasting_data_'
    termidlist = ['0', main_series_termid]
    optionslist = []
    templates_per_series = {}
    for child_series_termid in child_series.values():
        termidlist.append(child_series_termid)
    for termid_item in termidlist:
        templates_per_series[termid_item] = {}
        if termid_item == '0':
            suffix = ''
        else:
            suffix = '_' + termid_item
        for eachsetting in template_settings:
            optionslist.append(prefix + eachsetting + suffix)
    list_of_WPOptions = wp.call(GetOptions(optionslist))    
    for wp_Option in list_of_WPOptions:
        if wp_Option.name[len(prefix):] in template_settings:
            templates_per_series['0'][wp_Option.name[len(prefix):]] = wp_Option.value
        else:
            for termid_item in termidlist:
                suffix = '_' + termid_item
                if wp_Option.name[-len(suffix):] == suffix:
                    templates_per_series[termid_item][wp_Option.name[len(prefix):-len(suffix)]] = wp_Option.value
    
    timezone = get_localzone()
                
    for entry, details in sorted(list_from_csv.iteritems()):
        if not details['series'].lower() in child_series:
            wpseries = WordPressTerm()
            wpseries.taxonomy = 'series'
            wpseries.name = details['series']
            wpseries.parent = main_series_termid
            wpseries.id = wp.call(NewTerm(wpseries))
            child_series[details['series']] = wpseries.id
            listofseriesterms.append(wpseries)
            series[wpseries.id] = wpseries.name
            child_series[wpseries.name.lower()] = wpseries.id            
            if details['episode_number'] == '':
                details['episode_number'] = '1'
                child_series_existing_episode_numbers[wpseries.id] = 1
            else:
                child_series_existing_episode_numbers[wpseries.id] = int(details['episode_number'])
            details['seriesid'] = wpseries.id
        else:
            try:
                child_series_existing_episode_numbers[child_series[details['series'].lower()]] 
            except KeyError:
                for seriesterm in listofseriesterms:
                    if seriesterm.id == child_series[details['series'].lower()]:
                        child_series_existing_episode_numbers[child_series[details['series'].lower()]] = seriesterm.count
                    else:
                        child_series_existing_episode_numbers[child_series[details['series'].lower()]] = 0
            if details['episode_number'] == '':
                child_series_existing_episode_numbers[child_series[details['series'].lower()]] += 1
                details['episode_number'] = str(child_series_existing_episode_numbers[child_series[details['series'].lower()]])
            else:
                child_series_existing_episode_numbers[child_series[details['series'].lower()]] = int(details['episode_number'])
            details['seriesid'] = child_series[details['series'].lower()]
        for template_setting, detail in template_settings.iteritems():
            list = [details['seriesid'], main_series_termid, '0']
            while details[detail] == '':
                try:
                    details[detail] = templates_per_series[list.pop(0)][template_setting]
                except KeyError:
                    continue
        publishtime = gettime(details['time'])
        if publishtime:
            local_datetime = timezone.localize(datetime.combine(entry, publishtime.time()))
            details['post_date_gmt'] = local_datetime.astimezone(pytz.utc)
        newpost = WordPressPost()
        newpost.post_type = 'podcast'
        newpost.title = details['title']
        newpost.date = details['post_date_gmt']
        newpost.post_status = 'draft'
        newpost.content = details['content']
        newpost.terms = [wp.call(GetTerm('series', main_series_termid))]
        if details['seriesid']:
            newpost.terms.append(wp.call(GetTerm('series', details['seriesid'])))
        newpost.custom_fields = [{'key': 'preacher', 'value': details['preacher']},
                                 {'key': 'date_recorded', 'value': details['date_recorded']},
                                 {'key': 'bible_passage', 'value': details['bible_passage']},
                                 {'key': 'episode_number', 'value': details['episode_number']},
                                 {'key': 'publish_now', 'value': 'on'}
                                 ]
        newpost.id = wp.call(NewPost(newpost))
        if newpost.id:
            print('Created Post ID ' + str(newpost.id) + ' for date: ' + details['date_recorded'])
                
if __name__ == '__main__':
    main()