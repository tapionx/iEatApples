#!/usr/bin/env python

from pprint import pprint
import sys
import os
import tempfile
import shutil
import re
import zipfile
import plistlib
import json
from itertools import chain

class ParseIPA(object):
    # ParseIPA is based on https://github.com/apperian/iOS-checkIPA
    plist_file_rx = re.compile(r'Payload/.+?\.app/Info.plist$')
    metadata_file_rx = re.compile(r'^iTunesMetadata.plist$')
    xml_rx = re.compile(r'<\??xml')

    def __init__(self, ipa_filename):
        self.info_plist_data = {}
        self.provision_data = {}
        self.errors = []
        self.ipa_filename = ipa_filename
        self.full_path_plist_filename = ''
        self.temp_directory = ''
        self.verbose = False

    def get_filename_from_ipa(self, filetype):
        zip_obj = zipfile.ZipFile(self.ipa_filename, 'r')

        if filetype == 'Info':
            regx = ParseIPA.plist_file_rx
        elif filetype == "iTunesMetadata":
            regx = ParseIPA.metadata_file_rx
        else:
            raise "unknown typetype" % filetype

        filenames = zip_obj.namelist()
        filename = ''
        for fname in filenames:
            if regx.search(fname):
                filename = fname
                break
        return {'filename': filename, 'zip_obj': zip_obj}
        # end get_filename_from_ipa()

    def extract_plist_data(self, name):
        extract_info = self.get_filename_from_ipa(name)
        zip_obj = extract_info['zip_obj']
        plist_filename = extract_info['filename']

        data = {}
        if plist_filename == '':
            self.errors.append('%s.plist file not found in IPA' % name)
        else:
            content = zip_obj.read(plist_filename)
            if ParseIPA.xml_rx.match(content):
                data = plistlib.readPlistFromString(content)
            else:
                self.temp_directory = tempfile.mkdtemp()

                zip_obj.extract(plist_filename, self.temp_directory)
                fullpath_plist = '%s/%s' % (self.temp_directory, plist_filename)

                os_info = os.uname()
                if os_info[0] == 'Linux':
                    cmd = 'plistutil -i "%s" -o "%s"' % (fullpath_plist, fullpath_plist)
                else:
                    cmd = 'plistutil -convert xml1 "%s"' % fullpath_plist

                if self.verbose:
                    pprint(cmd)

                os.system(cmd)
                data = plistlib.readPlist(fullpath_plist)
                # end if plist == ''
        return data

    def extract_info_plist_data(self):
        self.info_plist_data = self.extract_plist_data('Info')

    def extract_itunes_meta_data(self):
        self.itunes_meta_data = self.extract_plist_data("iTunesMetadata")

    def is_valid_zip_archive(self):
        return zipfile.is_zipfile(self.ipa_filename)

def process_ipa(ipa_filename):
    errors = []
    parse = ParseIPA(ipa_filename)

    if not parse.is_valid_zip_archive():
        errors.append('not a valid zip archive [%s]' % ipa_filename)
    else:
        parse.extract_info_plist_data()
        #parse.extract_itunes_meta_data()
        errors.extend(parse.errors)

    if len(errors) == 0:
        plist_keys = [
            'CFBundleIdentifier',
            'CFBundleVersion',
            'CFBundleShortVersionString',
            'CFBundleExecutable',
            'CFBundleDisplayName',
            'DTPlatformVersion',
            'MinimumOSVersion',
            'UIDeviceFamily',
            'UIRequiredDeviceCapabilities',
            ]

        plist_values = dict((k, parse.info_plist_data[k]) for k in plist_keys if k in parse.info_plist_data)

        url_schemes = []
        for url_type in parse.info_plist_data.get('CFBundleURLTypes', []):
            for url_scheme in url_type.get('CFBundleURLSchemes', []):
                url_schemes.append(url_scheme)


        result = plist_values.copy()
        result['url_schemes'] = url_schemes
        #result['item_id'] = parse.itunes_meta_data['itemId']
        #result['name'] = parse.itunes_meta_data['itemName']

        # clean up tmp directory tree
        try:
            if parse.temp_directory != '':
                shutil.rmtree(parse.temp_directory)
        except IOError, ex:
            print('errore pulizia tmp', str(ex))

        return result

    else:
        pprint(errors)
        return None

def main():

    # sudo apt-get install libplist-utils

    if len(sys.argv) != 4:
        print
        print 'usage: python iHateApples.py app.ipa web.example.com /var/www/web'
        print
        sys.exit(1)

    ipa = sys.argv[1]
    server_name = sys.argv[2]
    base_dir = sys.argv[3]
    
    file_dir = os.path.dirname(os.path.realpath(__file__))

    result = process_ipa(ipa)

    app_version = result['CFBundleVersion']
    app_name = result['CFBundleDisplayName']
    app_id = result['CFBundleIdentifier']
    
    ipa_name = ipa.replace('.ipa', '')

    http_uri = 'https://' + server_name + '/ipa/' + ipa_name + '/' + app_version + '/'
    plist_http_uri = http_uri + ipa_name + '.plist' 
    ipa_http_uri = http_uri + ipa_name + '.ipa' 

    out_dir = os.path.join(base_dir, ipa_name, app_version)

    ipa_uri = out_dir + '/' + ipa_name + '.ipa'
    plist_uri = out_dir + '/' + ipa_name + '.plist'
    html_uri = out_dir + '/index.html'

    with open(file_dir + '/template.plist', 'r') as f:
        ipa_content = f.read()

    with open(file_dir + '/template.plist', 'r') as f:
        plist = f.read()

    with open(file_dir + '/template.html', 'r') as f:
        html = f.read()

    plist = plist.replace('{{APP_VERSION}}', app_version)
    plist = plist.replace('{{APP_NAME}}', app_name)
    plist = plist.replace('{{APP_ID}}', app_id)
    plist = plist.replace('{{IPA_URI}}', ipa_http_uri)

    html = html.replace('{{APP_VERSION}}', app_version)
    html = html.replace('{{APP_NAME}}', app_name)
    html = html.replace('{{APP_ID}}', app_id)
    html = html.replace('{{PLIST_URI}}', plist_http_uri)

    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

    with open(ipa_uri, 'w') as f:
        f.write(ipa_content)

    with open(plist_uri, 'w') as f:
        f.write(plist)

    with open(html_uri, 'w') as f:
        f.write(html)

    print 'Processing %s' % ipa_name
    print 'APP_ID:      ' + app_id
    print 'APP_NAME:    ' + app_name
    print 'APP_VERSION: ' + app_version
    print 'Writed files in ' + out_dir
    print 'INSTALL URI: ' + http_uri

if __name__ == '__main__':
    main()
