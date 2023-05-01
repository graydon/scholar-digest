#!/usr/bin/env python3
#
# Copyright 2018 Graydon Hoare <graydon@pobox.com>
# MIT license.
#
# This is a simple aggregator tool for google scholar emails.
#
# Despite my pleading (and promises from more than one google intern to try to
# fix it), google scholar alerts -- which are wonderfully useful! -- are
# practically much harder to use than necessary, for a few very fixable key
# reasons:
#
#   - They give you alert for _every_ watch you have! If a paper in some field
#     cites 12 people you're watching citations for, you get 12 emails. This is
#     the worst part.
#
#   - They don't batch anything, really. If I want to collect "Papers from the
#     last month or two" I have to open hundreds of emails.
#
#   - They don't let you filter out noise keywords or (worse) paywalled
#     publishers. Guess how much I want to be told there's a new thing I can
#     give springer $40 per article to read? Yeah, no.
#
#   - Annoying-but-tolerable: they give you a scholar URL that links through to
#     the actual paper, rather than the paper URL.
#
# So this script fixes these problems. You run it and it chews on your mailbox
# for a while and spits out a _single_ list of de-duplicated, filtered links
# directly to papers, listing _all_ the reasons you were notified about a single
# paper in a single record, which is much faster to scan through and pick out
# stuff you want to read.
#
#
# Setup is pretty simple:
#
#   - Set up API access from google for your gmail account and put token in
#     token.json, credentials in credentials.json
#
#   - Edit topic-blacklist.txt and/or nonfree-blacklist.txt to taste.
#
# Run the script, capture its output, do what you want with it. When done, go
# to your email box and delete all the remaining messages from scholar by
# hand. This script does not delete.
#

from __future__ import print_function
from googleapiclient.discovery import build
from httplib2 import Http
from oauth2client import file, client, tools

import urllib
from html.parser import HTMLParser
import base64
import re

# If modifying these scopes, delete the file token.json.
SCOPES = 'https://www.googleapis.com/auth/gmail.readonly'

author_rx = re.compile("^(.*) - new articles$")
citing_rx = re.compile("^(.*) - new citations$")
related_rx = re.compile("^(.*) - new related research$")

class Paper:
    def __init__(self, url, desc):
        self.url = url
        self.desc = desc
        self.author = set()
        self.citing = set()
        self.related = set()

    def note_subject(self, subject):
        am = author_rx.match(subject)
        if am:
            self.author.add(am.group(1))
            return
        cm = citing_rx.match(subject)
        if cm:
            self.citing.add(cm.group(1))
        rm = related_rx.match(subject)
        if rm:
            self.related.add(rm.group(1))

    def dump(self):
        print("---")
        print("\t" + self.desc)
        print("\t" + self.url)
        if len(self.author) != 0:
            print("\tauthor: " + ", ".join(self.author))
        if len(self.citing) != 0:
            print("\tciting: " + ", ".join(self.citing))
        if len(self.related) != 0:
            print("\trelated: " + ", ".join(self.related))



class ScholarScraper(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self)
        self.papers = dict()
        self.pending_subject = None
        self.pending_url = None

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        if tag == 'a' and attr_dict.get('class', None) == 'gse_alrt_title':
            scholar_url = attr_dict.get('href', '')
            parsed = urllib.parse.urlparse(scholar_url)
            qdict = urllib.parse.parse_qs(parsed.query)
            if 'url' in qdict:
                self.pending_url = str(qdict['url'][0])

    def handle_endtag(self, tag):
        if self.pending_url is not None:
            self.pending_url = None

    def handle_data(self, data):
        if self.pending_url is not None:
            if self.pending_url not in self.papers:
                self.papers[self.pending_url] = Paper(self.pending_url, data)
            paper = self.papers[self.pending_url]
            if self.pending_subject is not None:
                paper.note_subject(self.pending_subject)

    def set_subject(self, subject):
        self.pending_subject = subject.decode("utf-8")

    def dump(self):

        # Exclude paywalled links +/- your preferences
        nonfree_blacklist = [line.strip()
                             for line in open('nonfree-blacklist.txt')
                             if line.strip()]

        # Exclude topics +/- your preferences
        topic_blacklist = [line.strip()
                           for line in open('topic-blacklist.txt')
                           if line.strip()]

        for url, paper in self.papers.items():
            if not any([b in url for b in nonfree_blacklist]):
                ld = paper.desc.lower()
                if not any([t in ld for t in topic_blacklist]):
                    paper.dump()


def main():
    scraper = ScholarScraper()
    store = file.Storage('token.json')
    creds = store.get()
    if not creds or creds.invalid:
        flow = client.flow_from_clientsecrets('credentials.json', SCOPES)
        creds = tools.run_flow(flow, store)
    service = build('gmail', 'v1', http=creds.authorize(Http()))

    query = 'is:unread from:(scholaralerts-noreply@google.com)'
    maxRes = 10000
    response = service.users().messages().list(userId='me', q=query, maxResults=maxRes).execute()

    messages = []
    if 'messages' in response:
      messages.extend(response['messages'])

    while 'nextPageToken' in response:
      page_token = response['nextPageToken']
      response = service.users().messages().list(userId='me', q=query,
                                         pageToken=page_token).execute()
      messages.extend(response['messages'])

    print('Scanning %d messages...' % len(messages))
    for m in messages:
        msg = service.users().messages().get(userId='me', id=m['id']).execute()
        payload = msg['payload']
        subj = [h['value'] for h in payload['headers'] if h['name']=='Subject'][0]
        scraper.set_subject(subj.encode('utf-8'))
        v = payload['body']['data']
        scraper.feed(base64.urlsafe_b64decode(str(v)).decode("utf-8"))

    scraper.dump()

if __name__ == '__main__':
    main()
