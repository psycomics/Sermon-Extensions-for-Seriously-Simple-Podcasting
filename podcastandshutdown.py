#!/usr/bin/python

import subprocess
import datetime

subprocess.call(['/Audio/Podcasting/Wordpress_Auto_Podcasting/Python Script/ssp_sermon_podcast.py', '-l', '/Audio/Podcasting/Wordpress_Auto_Podcasting/ssp_sermon_podcast.log'])

if 'logged in' in subprocess.check_output(['last']):
    subprocess.call(['pmset', 'schedule', 'shutdown', (datetime.datetime.now()+datetime.timedelta(seconds=30)).strftime('%m/%d/%y %H:%M:%S')])
else:
    subprocess.call(['shutdown', '-h', '+1'])