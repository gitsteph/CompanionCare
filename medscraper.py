from bs4 import BeautifulSoup
import urllib2
import re
from collections import OrderedDict
import json

# download url and make into soup
def get_soup(url):
    print 'getting soup for', url
    req = urllib2.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        url = urllib2.urlopen(req, timeout=5.0).read()
    except:
        url = urllib2.urlopen(req, timeout=5.0).read()
    soup = BeautifulSoup(url, 'html.parser')
    return soup

def get_med(med_url='/pet-medication/acepromazine'):
    soup = get_soup('http://www.petmd.com' + med_url)

    # extract title before hyphen (the drug name)
    title = soup.title(text=True)
    title_dash_index = title[0].find(" -")
    title = title[0][:title_dash_index]
    print title

    # find the article body text and split into lines
    article_body = soup.find('div', {'itemprop': 'articleBody'})
    inner_article_body = article_body.find('p')
    article_body_text = inner_article_body.text
    article_body_list = article_body_text.split('\n')

    # helper to match headers, excluding unicode character
    def h23_but_not_crap(tag):
        return tag.name == "h2" or tag.name == "h3" and tag.text != u"\xa0"

    # main sections are marked by h2 or h3 tags
    article_tags_list = article_body.find_all(h23_but_not_crap)

    # special cases removed for now; they take some extra work to generalize across drug pages
    # # special handling to find drug reaction tag
    # interactions_str = re.compile(".* may react with these drugs:")
    # interactions_tag = article_body.find("p", string=interactions_str)
    # # special handling to find drug cautions tag
    # cautions_str = re.compile("USE CAUTION WHEN ADMINISTERING.*")
    # cautions_tag = article_body.find("p", string=cautions_str)

    # build a list of all section headers, to use later to split up the article
    # article_tags_list_strings = [(x.text.split('\n')[0]) for x in article_tags_list + [interactions_tag, cautions_tag] if x is not None]
    article_tags_list_strings = [(x.text.split('\n')[0]) for x in article_tags_list if x is not None]
    print article_tags_list_strings

    # find header indices in full article body list
    headers_index_list = []
    article_tags_set_strings = set(article_tags_list_strings)
    article_tags_in_order = []
    for i in xrange(len(article_body_list)):
        if article_body_list[i] in article_tags_set_strings:
            article_tags_in_order.append((i, article_body_list[i]))

    article_tags_list_strings = []
    for index,title_tag_string in article_tags_in_order:
        article_tags_list_strings.append(title_tag_string)
        headers_index_list.append(index)

    headers_index_list.append(-1)  # add a final index to read to the end of the list

    print headers_index_list

    petmd_dict = OrderedDict([])  # store the named sections of the article in a dict
    for i in xrange(len(article_tags_list_strings)):
        start = headers_index_list[i]+2
        end = headers_index_list[i+1]
        key = article_tags_list_strings[i]
        # if (key.startswith("USE CAUTION")):  # special case: cautions have no header string
        #     key = "Cautions"  # make our own header/title for cautions
        #     start -= 2  # move back so we don't miss the first caution

        petmd_dict[key] = petmd_dict.get(key, []) + article_body_list[start:end]

    print petmd_dict
    print petmd_dict.keys()

    return petmd_dict


def get_meds_list():
    soup = get_soup('http://www.petmd.com/pet-medication')

    rx_containers = soup.find_all('div', 'rx-sub-container')
    all_meds_list = []
    for rxc in rx_containers:
        medlinks_tags = rxc.find_all('a')
        all_meds_list += [(x['href'], x.text.strip()) for x in medlinks_tags]

    return all_meds_list


def sleep_randomly():
    import time
    import random
    sleep_time = 2 + random.random()*2
    print 'sleeping', sleep_time, 'seconds'
    time.sleep(sleep_time)

all_meds_dict = {}
with open('medications.json', 'r') as fp:
    all_meds_dict = json.load(fp)

# all_meds_list = [('/pet-medication/pancreatic-enzymes', 'Pancreatic Enzymes')]
all_meds_list = get_meds_list()

rescrape = False  # set this to True if you want to re-download+scrape medicines that are already in the json

for (med_url, med_name) in all_meds_list:
    sleep_randomly()

    print 'grabbing', med_name
    if rescrape or med_name not in all_meds_dict:
        all_meds_dict[med_name] = get_med(med_url)

        with open('medications.json', 'w') as fp:
            json.dump(all_meds_dict, fp, sort_keys=True, indent=4, separators=(',', ': '))

    print 'grabbed med', med_name
