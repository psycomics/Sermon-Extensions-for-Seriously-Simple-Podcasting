#!/usr/bin/python
# Copyright 2015 Chris Spalding (c_spalding@hotmail.com) - free for noncommercial use.
# version 0.1.6 - 7 April 2016
# Prototyped in Python 2.7.10 in Darwin on OS X 10.10.5

'''This is the companion Python script that will connect to Wordpress and use the
data entered in the Seriously Simple Podcasting and SSP Sermon extensions 
plugins, to process, encode, set the metadata of, upload and publish your audio
files to a podcast.

Requires:
- Wordpress - https://wordpress.org/
- Seriously Simple Podcasting - http://www.seriouslysimplepodcasting.com/
- Seriously Simple Podcasting Sermon Extensions (that'd be from wherever you got this script)
- Python-wordpress-xmlrpc - https://python-wordpress-xmlrpc.readthedocs.org/en/latest/index.html
- Pycrypto - https://www.dlitz.net/software/pycrypto/
- Command line based audio encoder e.g. Mac OS included afconvert or NeroAAC http://www.nero.com/ena/company/about-nero/nero-aac-codec.php
- Python Audio Tools - http://audiotools.sourceforge.net/
- Scriptures - http://www.davisd.com/python-scriptures/'''

'''todo:
- replace find with findtext on elements?
- enable EDITING of config file instead of replace
'''

# Import the modules we'll need to do this

import os
import re
import sys
import datetime
import ftplib
import subprocess
import types
import tempfile
import copy
import urllib2

from getpass import getpass
import binascii
from string import Template
from math import log10
from fractions import Fraction

import xml.etree.ElementTree as ET
from xml.dom import minidom

from wordpress_xmlrpc import Client, WordPressPost, WordPressTerm
from wordpress_xmlrpc.methods.taxonomies import GetTerms, GetTerm, NewTerm
from wordpress_xmlrpc.methods.options import GetOptions
from wordpress_xmlrpc.methods.posts import GetPosts, EditPost, GetPost

from Crypto.Cipher import AES
from Crypto import Random
import uuid

import audiotools, audiotools.replaygain, audiotools.pcmconverter
import scriptures


#define the helptext:
def helptext():
    print('\nThis is the companion Python script that will connect to Wordpress and use the \ndata entered in the Seriously Simple Podcasting and SSP Sermon extensions \nplugins, to process, encode, set the metadata of, upload and publish your audio \nfiles to a podcast. \n\nRequires:\n- Wordpress - https://wordpress.org/\n- Seriously Simple Podcasting - http://www.seriouslysimplepodcasting.com/\n- Seriously Simple Podcasting Sermon Extensions (that\'d be from wherever you got this script)\n- Python-wordpress-xmlrpc - https://python-wordpress-xmlrpc.readthedocs.org/en/latest/index.html\n- Pycrypto - https://www.dlitz.net/software/pycrypto/\n- Command line based audio encoder e.g. Mac OS included afconvert or NeroAAC http://www.nero.com/ena/company/about-nero/nero-aac-codec.php\n- Python Audio Tools - http://audiotools.sourceforge.net/\n- Scriptures - http://www.davisd.com/python-scriptures/')
    print('\nSettings are configured in an xml file in a default location (/etc).  \nYou can configure this on first run, or with the \'--config\' option.  \nYou may supply your own config file location with \'-c <filename>\'.\n Specify a logfile with \'-l <filename>\'.')
        
class LogFileSplitter(object):
    '''A file style class that will write to file1 and prepend the date to file2.
    usually you would redirect stdout to a LogFileSplitter object, then set file1 as
    stdout and file2 as a log file to write a timestamped log'''
    def __init__(self, file1, file2):
        self.file1 = file1
        self.file2 = file2
        self.at_start_of_line = True
    
    def write(self, somestring):
        if self.at_start_of_line == True:
            self.file2.write(datetime.datetime.now().replace(microsecond = 0).isoformat(' ') + ' ')
        self.file1.write(somestring)
        self.file2.write(somestring)
        try:
            self.at_start_of_line = (somestring[-1] == '\n')
        except:
            self.at_start_of_line = True
        
    def writelines(self, someiterable):
        if self.at_start_of_line == True:
            self.file2.write(datetime.datetime.now().replace(microsecond = 0).isoformat(' ') + '\n')
        self.file1.writelines(someiterable)
        self.file2.writelines(someiterable)
        try: 
            self.at_start_of_line = (somestring[-1][-1] == '\n')
        except:
            self.at_start_of_line = True
        
    def flush(self):
        self.file1.flush()
        self.file2.flush()
        
    def close(self):
        self.file1.close()
        self.file2.close()
        
def trimlogfile(file):
    '''Open the existing log file if there is one and trim it to a number of lines'''
    try: 
        existinglogfile = open(file, 'rU')
        existinglogentries = existinglogfile.readlines()
        existinglogfile.close()
        linestodelete = len(existinglogentries) - 15000
        if linestodelete > 0:
            del existinglogentries[0:linestodelete]
        existinglogfile = open(file, 'w')
        existinglogfile.writelines(existinglogentries)
        existinglogfile.close()
    except (OSError, IOError):
        print 'Log file not trimmed due to an error.'
    
def encryptpassword(clearpassword):
    if clearpassword:
        key = b'*,b0uPWLghSX1E-r2Qg/%vFgN' + str(uuid.getnode())[-7:]
        iv = Random.new().read(AES.block_size)
        cipher = AES.new(key, AES.MODE_CFB, iv)
        return binascii.hexlify(iv + cipher.encrypt(clearpassword))
    else:
        return ''
    
def decryptpassword(encryptedin):
    if encryptedin:
        encrypted = binascii.unhexlify(encryptedin)
        key = b'*,b0uPWLghSX1E-r2Qg/%vFgN' + str(uuid.getnode())[-7:]
        iv = encrypted[:AES.block_size]
        cipher = AES.new(key, AES.MODE_CFB, iv)
        decrypt = cipher.decrypt(encrypted)
        return decrypt[AES.block_size:]
    else:
        return ''
    
def get_post_custom_field(wpPostObject, fieldkey):
    '''returns the custom field value from the supplied WP Post that matches the key'''
    for custom_field in wpPostObject.custom_fields:
        if custom_field['key'] == fieldkey:
            return custom_field['value']
            break
            
def seriescfg_from_term_id(listofseriescfg, searched_term_id):
    for seriescfg in listofseriescfg:
        if seriescfg.get('term_id') == searched_term_id:
            return seriescfg
            break
            
def extension_dot(extension):
    '''prepends a dot to the extension if there isn't one supplied'''
    if type(extension) == types.StringType and extension[0] != '.':
        extension = '.' + extension.lower()
    elif type(extension) != types.StringType or extension == '':
        extension = None
    else:
        extension = extension.lower()
    return extension
    
def getaudioparams(audiotoolsobject):
    '''returns a little dict of audio file properties that can be fed back into subprocess args'''
    return {'sample_rate': str(audiotoolsobject.sample_rate), 
            'channels': str(audiotoolsobject.channels), 
            'bits_per_sample': str(audiotoolsobject.bits_per_sample)}
            
def getdatetime(datestring, default = None, user_format = None):
    '''this will try a few common date formats and return a datetime object if it can'''
    returndate = None
    if user_format:
        counter = 0
    else:
        counter = 1
    dateformats = {0: user_format, 1: '%d/%m/%Y', 2: '%b-%d %Y', 3: '%Y-%m-%d', 4: '%d-%m-%Y', 5: '%d %B, %Y'}
    while returndate == None and counter in dateformats:
        try:
            returndate = datetime.datetime.strptime(datestring, dateformats[counter])
        except ValueError:
            returndate = None
        counter += 1
    if returndate == None:
        return default
    else:
        return returndate
        
def make_podcast_dict(podcast_and_config, wp, settings, final_pass = False):
    '''returns a dictionary of podcast details, including substituting template details'''
    template_settings = {'ep_title_template': 'title',
                         'service_time' : 'time',
                         'service_name' : 'service_name',
                         'comments_template': 'content',
                         'image': 'image',
                         'owner_name': 'publisher',
                         'copyright': 'copyright',
                         'series_file_code': 'series_file_code',
                         'series_file_template': 'output_file_template'
                         }
    podcast = podcast_and_config[0]
    wp_details = {'title': podcast.title, 
                  'content': podcast.content, 
                  'date': podcast.date, 
                  'post_status': podcast.post_status, 
                  'slug': podcast.slug
                  }
    fields_of_interest = ['audio_file', 'bible_passage', 'duration', 'episode_number', 'filesize_raw', 'preacher', 'publish_now', 'date_recorded']
    for custom_fields in podcast.custom_fields:
        if custom_fields['key'] in fields_of_interest:
            wp_details[custom_fields['key']] = custom_fields['value']
    try:
        wp_details['image'] = podcast.thumbnail['link']
    except:
        wp_details['image'] = ''
    optionprefix = 'ss_podcasting_data_'
    podcast_terms = {}
    for term in podcast.terms:
        podcast_terms[term.id] = term.name
    for termid in podcast_and_config[3]:
        options_to_get = []
        if termid == '0':
            optionsuffix = ''
            lensuffix = None
        else:
            optionsuffix = '_' + termid
            lensuffix = -len(optionsuffix)
        for eachsetting, postsetting in template_settings.iteritems():
            if not postsetting in wp_details or not wp_details[postsetting]:
                options_to_get.append(optionprefix + eachsetting + optionsuffix)
        try:
            list_of_WPOptions = wp.call(GetOptions(options_to_get))
        except AttributeError:
            list_of_WPOptions = []
        for wpoption in list_of_WPOptions:
            wpoptionname = template_settings[wpoption.name[len(optionprefix):lensuffix]]
            wp_details[wpoptionname] = wpoption.value
        if not ('series' in wp_details) or wp_details['series'] == '':
            try:
                wp_details['series'] = podcast_terms[termid]
            except KeyError:
                pass
    if 'date_recorded' in wp_details:
        wp_details['date_recorded_datetime'] = getdatetime(wp_details['date_recorded'], user_format = settings.find('date_recorded_format').text)
    #clean out blank items so that the template will remain intact for another pass after publishing (so the slug will be updated).
    if not final_pass:
        keys_to_delete = []
        for detail_name, detail_content in wp_details.iteritems():
            if not detail_content:
                keys_to_delete.append(detail_name)
        for key_to_delete in keys_to_delete:
            del wp_details[key_to_delete]
    #iterate over the dictionary to substitute:
    for detail_name, detail_content in wp_details.iteritems():
        if type(detail_content) == types.UnicodeType:
            detail_content = detail_content.encode('ascii', 'ignore')
        if type(detail_content) == types.StringType:
            try:
                dated_detail_content = wp_details['date_recorded_datetime'].strftime(detail_content)
            except:
                print('Unable to substitute date into ' + detail_name + ' : ' + detail_content)
                dated_detail_content = detail_content
            muted_wp_details = copy.copy(wp_details)
            muted_wp_details[detail_name] = ''
            wp_details[detail_name] = Template(dated_detail_content).safe_substitute(muted_wp_details)
    return wp_details
    
def publish_post(podcast_and_config, wp_details, wp, settings):
    '''copies the podcast object, updates it according to the supplied details dict and edits the one on the blog'''
    podcastcopy = copy.copy(podcast_and_config[0])
    podcastcopy.title = wp_details['title']
    podcastcopy.content = wp_details['content']
    podcastcopy.date = wp_details['date']
    podcastcopy.post_status = wp_details['post_status']
    if type(podcast_and_config[0].thumbnail) == types.DictType:
        podcastcopy.thumbnail = podcast_and_config[0].thumbnail['attachment_id']
    fields_of_interest = ['audio_file', 'bible_passage', 'duration', 'episode_number', 'filesize_raw', 'preacher', 'publish_now', 'date_recorded']
    for custom_fields in podcastcopy.custom_fields:
        if custom_fields['key'] in fields_of_interest and custom_fields['key'] in wp_details:
            custom_fields['value'] = wp_details[custom_fields['key']]
            fields_of_interest.remove(custom_fields['key'])
    for custom_field in fields_of_interest:
        if custom_field in wp_details:
            podcastcopy.custom_fields.append({'key': custom_field, 
                                              'value': wp_details[custom_field]
                                              })
    if 'tags' in wp_details and wp_details['tags'] != []:
        podcastcopy.terms.extend(wp_details['tags'])    
    if wp.call(EditPost(podcastcopy.id, podcastcopy)):
        return wp.call(GetPost(podcastcopy.id))
    else:
        print('Could not update podcast ' + podcastcopy.id + ': ' + podcastcopy.title)     
        
def printhash(unusedinput):
    '''just a callback for the ftp function to make the hashes we like to see to show something is happening'''
    sys.stdout.write('#')
    sys.stdout.flush()

def ftp_encodedfile(encodedfilepath, filename, termid_seriesconfig):
    '''open the FTP connection and change to the destination path, A
    trying to catch most exceptions along the way, ftp cmd and resp will be printed
    some exceptions will still be raised, so try: this function.'''
    print('\n')
    print('Opening the FTP connection ...')
    ftp = ftplib.FTP()
    ftp.set_debuglevel(1)
    ftp.connect(termid_seriesconfig.findtext('ftp_host'), int(termid_seriesconfig.findtext('ftp_port')))
    ftp.login(termid_seriesconfig.findtext('ftp_user'),decryptpassword(termid_seriesconfig.findtext('ftp_pass')))
    ftp.set_pasv(True)
    try: 
        ftp.cwd(termid_seriesconfig.findtext('ftp_path'))
    except ftplib.error_perm as errcode:
        error = str(errcode)
        if error[0:3] == '550':
            print('The path ' + termid_seriesconfig.findtext('ftp_path') + ' doesn\'t exist on the FTP server, creating it.')
            ftp.mkd(termid_seriesconfig.findtext('ftp_path'))
            ftp.cwd(termid_seriesconfig.findtext('ftp_path'))
        else:
            raise ftplib.error_perm(errcode)
    print('\n')
    print('Attempting to send ' + filename)
    # we'll try up to three times if it doesn't work.
    destsize = 0
    errcounter = 0
    while errcounter < 3:
        if errcounter > 0:
            print('\nTrying again ...')
        try:
            encodedfile.close()
        except:
            pass
        encodedfile = open(encodedfilepath, 'rb')
        try:
            ftp.storbinary('STOR ' + filename, encodedfile, 8192, printhash)
            sourcesize = os.path.getsize(encodedfilepath)
            try:
                destsize = ftp.size(filename)
            except ftplib.all_errors:
                destsize = sourcesize
                try:
                    ftpnlst = ftp.nlst()
                except ftplib.all_errors:
                    ftpnlst = []
                    print('Can\'t get ftp directory listing.')
                if not filename in ftpnlst:
                    destsize = 0
            if sourcesize != destsize:                    
                print('The file sizes don\'t match: the original was ' + str(srcsize) + ' bytes, \nbut the file that ended up on the FTP server is only ' + str(dstsize))
                errcounter += 1
                print('Deleting incomplete file so as not to leave a mess.')
                try:
                    ftp.delete(filename)
                except ftplib.all_errors as message:
                    print('Couldn\'t delete that file - check what ended up there!')
                    print(str(message))
            else:
                print(str(destsize) + ' bytes transferred successfully.')
                errcounter = 100
        except IOError as errcode:
            print('!!!')
            print('!!!That didn\'t work: ' + str(errcode))
            errcounter += 1
            time.sleep(2)
            try: 
                print('\nQuitting and re-opening the ftp.')     # So, I don't really want to have to do this, BUT there seems to be a bug that the exceptions don't come back properly from the FTP and normal messages are received as errors.  I think for IO ERRORS.  And I know this try will fail, but I hope the FTP server still gets a reasonably polite disconnect just by trying.
                ftp.quit()
            except:
                ftp.close()
                print('Had to force it closed.')
            try: 
                ftp = ftplib.FTP()
                ftp.set_debuglevel(1)
                ftp.connect(termid_seriesconfig.findtext('ftp_host'), int(termid_seriesconfig.findtext('ftp_port')))
                ftp.login(termid_seriesconfig.findtext('ftp_user'),decryptpassword(termid_seriesconfig.findtext('ftp_pass')))
                ftp.set_pasv(True)
                ftp.cwd(termid_seriesconfig.findtext('ftp_path'))
            except ftplib.all_errors:
                print('Something went wrong there.')
            print('Deleting incomplete file so as not to leave a mess.')
            try:
                ftp.delete(filename)
            except ftplib.all_errors as message:
                print('Couldn\'t delete that file - check what ended up there!')
                print(str(message))
        except ftplib.all_errors as errcode:
            print('!!!')
            print('!!!That didn\'t work: ' + str(errcode))
            errcounter += 1
            time.sleep(2)
            ftp.abort()
            print('Deleting incomplete file so as not to leave a mess.')
            try:
                ftp.delete(filename)
            except ftplib.all_errors as message:
                print('Couldn\'t delete that file - check what ended up there!')
                print(str(message))
# close the ftp connection
    try: 
        ftp.quit()
    except ftplib.all_errors:
        print('The connection didn\'t quit nicely, so it\'s being closed.')
        try:
            ftp.close()
        except ftplib.all_errors:
            print('That might not have worked either.')
    encodedfile.close()
    
    if errcounter == 100:
        return str(destsize)
    else:
        return None
        
def configprompting(fields_dict):
    settings = ET.Element('config_subelement')
    for fieldname, fieldtuple in sorted(fields_dict.iteritems(), key = lambda x: x[1][2]):
        if fieldname[-4:] == 'pass':
            fieldtext = getpass(fieldtuple[0] + '\n')
            encfieldtext = encryptpassword(fieldtext)
            ET.SubElement(settings, fieldname).text = encfieldtext
        elif type(fieldtuple[1]) == types.ListType:
            space = ' '
            default = space.join(fieldtuple[1])
            firstinput = raw_input(fieldtuple[0] + '\n[' + default + ']')
            if firstinput:
                fieldtextlist = [firstinput]
                nextinput = raw_input()
                while nextinput:
                    fieldtextlist.append(nextinput)
                    nextinput = raw_input()
            else:
                fieldtextlist = fieldtuple[1]
            for fieldtext in fieldtextlist:
                ET.SubElement(settings, fieldname).text = fieldtext
        else:
            fieldtext = raw_input(fieldtuple[0] + '\n[' + fieldtuple[1] + ']')
            if not fieldtext:
                fieldtext = fieldtuple[1]
            ET.SubElement(settings, fieldname).text = fieldtext
    return settings
    
#define the config file creation function:    
def edit_config_file(configfile):
    '''if os.path.isfile(configfile):
        oldconfigET = ET.parse(configfile)
        oldconfig = oldconfigET.getroot()
        if not ((oldconfig.tag == 'config') and (oldconfig.attrib['description'] == 'Seriously Simple Podcasting Sermon Podcast settings')):
            print(configfile + ' is not a SSP Sermon Podcast config file, create a new one? (Y/N):')
            if not raw_input().lower() == 'y':
                print('OK, exiting')
                sys.exit(0)
            oldconfig = ET.Element('empty')'''
    
            
    #we're going to come back to the idea of editing an old config file - for now, this will just build a new one.

    #Starting a new XML element tree.
    newconfig = ET.Element('config', attrib = {'description' : 'Seriously Simple Podcasting Sermon Podcast settings'})
        
    #make a dict of settings tags to iterate over - with a tuple of the prompt, followed by defaults.
    setting_fields = {'wordpress_url': ('What is the URL of your WordPress Blog?.', '', 0),
        'wordpress_user': ('Enter the WordPress User name.', '', 1),
        'wordpress_pass': ('Enter your WordPress Password (will appear blank).', '', 2),
        'date_recorded_format': ('Enter the format of the \'date_recorded\' custom field', '%d-%m-%Y', 3),
        'source_audio_type': ('Enter the extension for the source audio', 'wav', 4),
        'target_loudness': ('Enter the target loudness as an integer (LKFS).', '-24', 5),
        'audiochannels': ('To convert to mono, enter \'1\', stereo, enter \'2\' or anything else for no conversion.', '2', 6),
        'bitspersample': ('Enter target bits per sample as an integer.', '16', 7),
        'processing_utility': ('If using a command line processing utility, enter its path and name.', 'stereo_tool_mac', 8),
        'processing_utility_arg': ('Enter the command line arguments for the processing utility.\nYou may use $sample_rate, $channels and $bits_per_sample of the input.  \nPress enter after each argument (spaces only in paths).', ['-s', 'sermonsettings.sts', '-r', '$sample_rate'], 9),
        'processing_utility_infile': ('If you need an argument before the input file, enter it.', '', 10),
        'processing_utility_outfile': ('If you need an argument before the output file, enter it.', '', 11),
        'encoding_utility': ('Enter the path and name to the encoding utility.', 'afconvert', 12),
        'encoding_utility_arg': ('Enter the command line arguments for the encoding utility.\nYou may use $sample_rate, $channels and $bits_per_sample of the input.  \nPress enter after each argument (spaces only in paths).', ['-d', 'aach@$sample_rate', '-c', '1', '-s', '3', '-u', 'vbrq', '35', '--soundcheck-generate', '-l', 'Mono', '--profile', '-f', 'mp4f', '-q', '127'], 13),
        'encoding_utility_infile': ('If you need an argument before the input file, enter it.', '', 14),
        'encoding_utility_outfile': ('If you need an argument before the output file, enter it.', '', 15),
        'encoded_audio_type': ('Enter the extension for the encoded audio', 'm4a', 16)}
    
    print('Enter your settings as follows.  If you want the default, press enter.')

    settings = ET.SubElement(newconfig, 'settings')
    settings.extend(configprompting(setting_fields))

    wordpress_url = settings.find('wordpress_url').text
    if wordpress_url.endswith('/'):
        xmlrpc_url = wordpress_url + 'xmlrpc.php'
    else:
        xmlrpc_url = wordpress_url + '/xmlrpc.php'
    
    print('Connecting to WordPress Blog and finding series ...')    
    
    #try:
    wp = Client(xmlrpc_url, settings.find('wordpress_user').text, decryptpassword(settings.find('wordpress_pass').text))
    listofseriesterms = wp.call(GetTerms('series')) 
    
    seriescfg_fields = {'source_path': ('What is the path where the source audio is for this series?', '', '0'),
        'source_date_format': ('Source audio file names must start with a date, what is its format?', '%Y-%m-%d', 1),
        'source_file_code': ('The code following the date in the  source files for this series', '', 2),
        'ftp_host': ('What is the host address of the FTP server?', '', 3),
        'ftp_port': ('What is the FTP server port?', '21', 4),
        'ftp_user': ('What is the username for the FTP server?', '', 5),
        'ftp_pass': ('What is the password for the FTP server?', '', 6),
        'ftp_path': ('What is the relative path on the FTP server to save this series to?', '', 7),
        'download_path': ('Enter the path where the file will be downloaded from', '', 8)}        
    
    for seriesterm in listofseriesterms:
        if raw_input('Do you want to upload to the series named \'' + seriesterm.name + '\'? (Y/N)\n').lower() == 'y':
            seriescfg = ET.SubElement(newconfig, 'series_config', attrib = {'term_id': seriesterm.id, 'name': seriesterm.name})
            seriescfg.extend(configprompting(seriescfg_fields))

    minidomparsed = minidom.parseString(ET.tostring(newconfig))
    cfgfile_object = open(configfile, 'w')
    minidomparsed.writexml(cfgfile_object, indent='', addindent='    ', newl='\n')
    cfgfile_object.close()

# define the main function of the script
def main():
# look for command line arguments
    args = sys.argv[1:]
    
    if '-h' in args or '--help' in args or '-?' in args:
        helptext()
        sys.exit(0)
    
    if '-l' in args:
        logging = True
        logfilename = args[args.index('-l') + 1]
        trimlogfile(logfilename)
        logfile = open(logfilename, 'a')
        oldstdout = sys.stdout
        oldstderr = sys.stderr
        logsplit = LogFileSplitter(sys.stdout, logfile)
        sys.stdout = logsplit
        sys.stderr = logsplit
        print('Logging started.')
    
    if '-c' in args:
        configfile = args[args.index('-c') + 1]
        if not os.path.isfile(configfile):
            print(configfile + ' does not exist, create it? (Y/N):')
            if not raw_input().lower() == 'y':
                print('OK, config file will not be created')
                if logging == True:
                    sys.stdout = oldstdout
                    sys.stderr = oldstderr
                    logfile.close()
                sys.exit(0)
    else:
        configfile = '/etc/ssp_sermon_podcast.xml'
        
    if ('--config' in args) or not os.path.isfile(configfile):
        edit_config_file(configfile)  
        print('Config file created and will be used on next run.')  
        if logging:
            sys.stdout = oldstdout
            sys.stderr = oldstderr
            logfile.close()
        sys.exit(0)
    
    #load the config file    
    if os.path.isfile(configfile):
        try:
            configET = ET.parse(configfile)
        except:
            print('Can\'t parse config file ' + configfile)
            sys.exit(1)
        config = configET.getroot()
        if not ((config.tag == 'config') and (config.attrib['description'] == 'Seriously Simple Podcasting Sermon Podcast settings')):
            print(configfile + ' is not a SSP Sermon Podcast config file.')
            if logging:
                sys.stdout = oldstdout
                sys.stderr = oldstderr
                logfile.close()
            sys.exit(1)
    
    #get the settings from the config
    settings = config.find('settings')
    
    #open the wordpress object
    wordpress_url = settings.find('wordpress_url').text
    if wordpress_url.endswith('/'):
        xmlrpc_url = wordpress_url + 'xmlrpc.php'
    else:
        xmlrpc_url = wordpress_url + '/xmlrpc.php'

    wp = Client(xmlrpc_url, settings.find('wordpress_user').text, decryptpassword(settings.find('wordpress_pass').text))
    
    #get a list of podcast objects
    allpodcasts = []
    interval = 20
    offset = 0
    while True:
        podcastbatch = wp.call(GetPosts({'post_type' : 'podcast', 'number': interval, 'offset': offset}))
        if len(podcastbatch) == 0:
            break
        allpodcasts.extend(podcastbatch)
        offset += interval
        
    print('Retrieved ' + str(len(allpodcasts)) + ' podcasts from WordPress site.')
    
    #get the series settings from the config and find out which series will be podcast
    allseriesconfigs = config.findall('series_config')
    termids_to_podcast = []
    for seriesconfig in allseriesconfigs:
        termids_to_podcast.append(seriesconfig.attrib['term_id'])
    
    #get a list of series from the blog
    listofseriesterms = []
    interval = 20
    offset = 0
    while True:
        termsbatch = wp.call(GetTerms('series', {'number': interval, 'offset': offset}))
        if len(termsbatch) == 0:
            break
        listofseriesterms.extend(termsbatch)
        offset += interval
    
    print('Found ' + str(len(listofseriesterms)) + ' podcast series on the WordPress site.')
    
    #find out the hierarchy of the series so we can do the lowest children first
    termpriority = {}
    term_parents = {}
    
    for term in listofseriesterms:
        term_parents[term.id] = term.parent
        order = 0
        parentid = term.parent
        while parentid != '0':
            order += 1
            for parentterm in listofseriesterms:
                if parentid == parentterm.id:
                    parentid = parentterm.parent
                    break
        termpriority[term.id] = order
        
    #so the order to approach term.ids is
    termid_order = []
    
    for termid, order in sorted(termpriority.iteritems(), key = lambda x: x[1], reverse = True):
        termid_order.append(termid)
        
    print('This is the order the series terms will be published:')
    print(', '.join(termid_order))
    
    #find which series config the posts should be published with (if any)
    podcasts_to_do = {}
    extension = extension_dot(settings.findtext('source_audio_type'))
    for termid in termid_order:
        if termid in termids_to_podcast:
            for podcast in allpodcasts:
                #check whether the podcast is flagged to be published and has a date:
                date_recorded = get_post_custom_field(podcast, 'date_recorded')
                if get_post_custom_field(podcast, 'publish_now') and date_recorded:
                    podcast_termids = ['0']
                    for podcastterm in podcast.terms:
                        podcast_termids.append(podcastterm.id)
                    for podcast_termid in podcast_termids:
                        if podcast_termid in term_parents:
                            podcast_termids.append(term_parents[podcast_termid])
                    if termid in podcast_termids and not podcast.id in podcasts_to_do:
                        #work out what the start of the source file name will be:
                        termid_seriesconfig = seriescfg_from_term_id(allseriesconfigs, termid)
                        source_date_format = termid_seriesconfig.find('source_date_format').text
                        date_recorded_format = settings.find('date_recorded_format').text
                        sourcefile_name_start = getdatetime(date_recorded, user_format = date_recorded_format).strftime(source_date_format) + termid_seriesconfig.findtext('source_file_code', default = '')
                        sourcepath = termid_seriesconfig.findtext('source_path')
                        #and does it exist?
                        directorylist = []
                        if os.path.exists(sourcepath):
                            #this seems to timeout sometimes, so will loop if need be:
                            retrycount = 3
                            while retrycount:
                                try:
                                    directorylist = os.listdir(sourcepath)
                                    retrycount = 0
                                except OSError as errmsg:
                                    print(errmsg)
                                    retrycount -= 1
                                    if retrycount:
                                        print('Retrying directory list...')                                    
                        for filename in directorylist:
                            if filename[:len(sourcefile_name_start)] == sourcefile_name_start:
                                if extension:
                                    extposn = -len(extension)
                                if filename[extposn:] == extension or extension == None:
                                    ordered_podcast_termids = []
                                    for termid_again in termid_order:
                                        if termid_again in podcast_termids:
                                            ordered_podcast_termids.append(termid_again)
                                    ordered_podcast_termids.append('0')
                                    podcasts_to_do[podcast.id] = [podcast, termid_seriesconfig, os.path.abspath(os.path.join(sourcepath,filename)), ordered_podcast_termids]
    
    print('There are ' + str(len(podcasts_to_do)) + ' podcasts to process in this pass.')
    
    if len(podcasts_to_do) != 0:
        listofposttags = []
        interval = 20
        offset = 0
        while True:
            termsbatch = wp.call(GetTerms('post_tag', {'number': interval, 'offset': offset}))
            if len(termsbatch) == 0:
                break
            listofposttags.extend(termsbatch)
            offset += interval
        posttagsdict = {}
        for posttag in listofposttags:
            posttagsdict[posttag.name.lower()] = posttag
        print('Retrieved ' + str(len(posttagsdict)) + ' post tags from WordPress site.')
        
    #iterate over the podcasts
    for podcast_id, podcast_and_config in podcasts_to_do.iteritems():
        #open the audio file
        print('\n')
        print('Now processing file ' + podcast_and_config[2])
        backuppodcast = copy.deepcopy(podcast_and_config[0])
        try:
            sourceaudio = audiotools.open(podcast_and_config[2])
            sourcepcm = sourceaudio.to_pcm()                
        
            #calculate its loudness
            loudness = audiotools.calculate_replay_gain([sourceaudio])
            for loudnesstuple in loudness:
                gain = loudnesstuple[1]
                peak = loudnesstuple[2]
            if peak == 0:
                print('This audio file is silent, ignoring it.')
                continue

            #mix it to the specified number of channels
            gaincorrection = 0
            if settings.findtext('audiochannels') == '1':
                print('Converting to mono.')
                sourcepcm_mixed = audiotools.pcmconverter.Averager(sourcepcm)
            elif settings.findtext('audiochannels') == '2':
                print('Converting to stereo.')
                sourcepcm_mixed = audiotools.pcmconverter.Downmixer(sourcepcm)
                if sourceaudio.channels() == 1:
                    gaincorrection = 6.0
            else:
                sourcepcm_mixed = sourcepcm
        
            #adjust the gain to the users' preference instead of replaygain's target -20
            target_loudness = float(settings.findtext('target_loudness', default = '-24'))
            newgain = gain + (target_loudness + 20.0) + gaincorrection
            newpeak = 1.0 / (10.0 ** (newgain/20.0))
            if (peak / (10.0 ** (gaincorrection/20.0))) > newpeak:
                newpeak = peak / (10.0 ** (gaincorrection/20.0)) 
            print('Normalising for gain: ' + str(round(newgain, 2)) + 'dB, peak = ' + str(round((20.0*log10(peak / (10.0 ** (gaincorrection/20.0)))), 2)) + 'dBFS.')
            #normalise the audio to the target loudness
            sourcepcm_normalised = audiotools.replaygain.ReplayGainReader(sourcepcm_mixed, newgain, newpeak)
        
            try:
                bitspersample = int(settings.findtext('bitspersample'))
            except:
                bitspersample = None
            if bitspersample:
                print('Quantising to ' + str(bitspersample) + '-bit.')
                sourcepcm_resampled = audiotools.pcmconverter.BPSConverter(sourcepcm_normalised, bitspersample)
        
            #make some tempfiles:
            process_tempfile = tempfile.mkstemp(suffix = '.wav', prefix = 'sermon_process_tempfile')
            processed_tempfile = tempfile.mkstemp(suffix = '.wav', prefix = 'sermon_processed_tempfile')
            encoded_tempfile = tempfile.mkstemp(suffix = extension_dot(settings.findtext('encoded_audio_type')), prefix = 'sermon_encoded_tempfile')
            print('tempfiles: ' + process_tempfile[1] + ', ' + processed_tempfile[1] + ', ' + encoded_tempfile[1])
        
            #write the audio back out to a wave file for processing
            audiotools.WaveAudio.from_pcm(process_tempfile[1], sourcepcm_resampled)
        
            sourcepcm_normalised.close()
            sourcepcm_mixed.close()
            sourcepcm.close()
            sourceaudio = None
        
            audioparams = getaudioparams(sourcepcm_resampled) 
            sourcepcm_resampled.close()
            subprocess_args = [settings.findtext('processing_utility')]        
            for argsubelement in settings.findall('processing_utility_arg'):
                subprocess_args.append(Template(argsubelement.text).substitute(audioparams))
            tempstring = settings.findtext('processing_utility_infile')
            if tempstring:
                subprocess_args.append(tempstring)
            subprocess_args.append(process_tempfile[1])
            tempstring = settings.findtext('processing_utility_outfile')
            if tempstring:
                subprocess_args.append(tempstring)
            subprocess_args.append(processed_tempfile[1])
        
            print('Now processing audio ...')
        
            print(subprocess.Popen(subprocess_args, stdout = subprocess.PIPE, stderr = subprocess.STDOUT, universal_newlines = True).communicate()[0])
            os.remove(process_tempfile[1])
        
            processedfile = audiotools.open(processed_tempfile[1])
            audioparams = getaudioparams(processedfile.to_pcm())
            subprocess_args = [settings.findtext('encoding_utility')]        
            for argsubelement in settings.findall('encoding_utility_arg'):
                subprocess_args.append(Template(argsubelement.text).substitute(audioparams))
            tempstring = settings.findtext('encoding_utility_infile')
            if tempstring:
                subprocess_args.append(tempstring)
            subprocess_args.append(processed_tempfile[1])
            tempstring = settings.findtext('encoding_utility_outfile')
            if tempstring:
                subprocess_args.append(tempstring)
            subprocess_args.append(encoded_tempfile[1])
        
            print('Now encoding audio ...')
        
            print(subprocess.Popen(subprocess_args, stdout = subprocess.PIPE, stderr = subprocess.STDOUT, universal_newlines = True).communicate()[0])
            os.remove(processed_tempfile[1])
        
            wp_details = make_podcast_dict(podcast_and_config, wp, settings)
        
            wp_details['post_status'] = 'publish'
            wp_details['publish_now'] = ''
        
            updated_podcast = publish_post(podcast_and_config, wp_details, wp, settings)
            podcast_and_config[0] = updated_podcast
            updated_details = make_podcast_dict(podcast_and_config, wp, settings, final_pass = True)
        
            try:
                imageurl = urllib2.urlopen(updated_details['image'])
                podcastimage = imageurl.read()
            except:
                podcastimage = False
            try:
                audioimage = [audiotools.Image.new(podcastimage, u'Artwork', 0)]
            except:
                audioimage = []
            outputmetadata = audiotools.MetaData(track_name = updated_details['title'], 
                                                 track_number = int(updated_details['episode_number']),
                                                 album_name = updated_details['series'],
                                                 artist_name = updated_details['preacher'],
                                                 copyright = updated_details['copyright'],
                                                 publisher = updated_details['publisher'],
                                                 year = updated_details['date'].strftime('%Y'),
                                                 date = updated_details['date_recorded'],
                                                 comment = updated_details['content'],
                                                 images = audioimage)
            outputfile = audiotools.open(encoded_tempfile[1])
            outputfile.set_metadata(outputmetadata)
            outputfile_seconds = int(outputfile.seconds_length())
        
            outputfile_name = updated_details['output_file_template'] + extension_dot(settings.findtext('encoded_audio_type'))
        
            outputfile_size = ftp_encodedfile(encoded_tempfile[1], outputfile_name, podcast_and_config[1])
            if outputfile_size == None:
                raise Exception('FTP appears not to have worked.')
        
            print('\n')
            print('Output file size = ' + str(outputfile_size))
            print('Output file duration = ' + str(outputfile_seconds))
            print('\n')
        
            os.remove(encoded_tempfile[1])
        
            urlpath = podcast_and_config[1].findtext('download_path')
            if not urlpath[-1] == '/':
                urlpath = urlpath + '/'     
            updated_details['audio_file'] = urlpath + outputfile_name
            updated_details['filesize_raw'] = str(outputfile_size)
            mins = str(outputfile_seconds / 60)
            secs = str(outputfile_seconds % 60)
            if len(secs) == 1:
                secs = '0' + secs
            updated_details['duration'] = mins + ':' + secs
        
            #put the preacher in as a tag:
            updated_details['tags'] = []
            if updated_details['preacher'].lower() in posttagsdict:
                updated_details['tags'].append(posttagsdict[updated_details['preacher'].lower()])
            else:
                tag = WordPressTerm()
                tag.taxonomy = 'post_tag'
                tag.name = updated_details['preacher']
                tag.id = wp.call(NewTerm(tag))
                updated_details['tags'].append(tag)
                posttagsdict[tag.name.lower()] = tag
        
            #put the book(s) of the bible in as tags:
            #This bit is really messy and I should try to write my own scripture regular expressions, but in the interest of speed:   
            listofpassages = scriptures.extract(updated_details['bible_passage'])
            if 'song of songs' in updated_details['bible_passage'].lower():
                listofpassages.append(('Song of Songs', 1, 1, 1, 1))
            for passage in listofpassages:
                book = passage[0]
                if book[:4] == 'III ':
                    bookname = '3 ' + book[4:]
                elif book[:3] == 'II ':
                    bookname = '2 ' + book[3:]
                elif book[:2] == 'I ':
                    bookname = '1 ' + book[2:]
                elif book == 'Song of Solomon':
                    bookname = 'Song of Songs'
                else:
                    bookname = book
                if bookname.lower() in posttagsdict:
                    updated_details['tags'].append(posttagsdict[bookname.lower()])
                else:
                    tag = WordPressTerm()
                    tag.taxonomy = 'post_tag'
                    tag.name = bookname
                    tag.id = wp.call(NewTerm(tag))
                    updated_details['tags'].append(tag)
                    posttagsdict[tag.name.lower()] = tag
        
            finalpost = publish_post(podcast_and_config, updated_details, wp, settings)
        
            print('Final Post details are as follows:\n')
        
            for field, contents in finalpost.struct.iteritems():
                try:
                    if type(contents) == types.StringType:
                        print(field + ' : ' + contents)
                    elif type(contents) == types.ListType:
                        for subcontents in contents:
                            print(field + ' : ' + str(subcontents))
                    elif type(contents) == types.DictType:
                        for subfield, subcontents in contents.iteritems():
                            print(field + ' : ' + subfield + ' : ' + str(subcontents))
                    elif type(contents) == types.UnicodeType:
                        print(field + ' : ' + contents.encode('ascii', 'ignore'))                        
                    else:
                        print(field + ' : ' + str(contents))      
                except:
                    print('Can\'t print field')
        except Exception as message:
            print('ERROR: Exception raised while processing that podcast:')
            print(message)
            print('Attempting to restore original post prior to modification...')
            try:
                if wp.call(EditPost(backuppodcast.id, backuppodcast)):
                    print('Post restored.')
                else:
                    print('Unable to restore original post.')
            except Exception as message:
                print('Unable to restore original post: ')
                print(message)
            try:
                os.remove(encoded_tempfile[1])
            except:
                pass
            try:
                os.remove(processed_tempfile[1])
            except:
                pass
            try:
                os.remove(process_tempfile[1])
            except:
                pass
                    
    logsplit.write('Completed with normal exit\n\n\n')    
    if logging:
        sys.stdout = oldstdout
        sys.stderr = oldstderr
        logfile.close()

# this bit calls the main function to make it run if the file is called
if __name__ == '__main__':
    main()