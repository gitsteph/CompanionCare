from bs4 import BeautifulSoup
import urllib2
import re
from collections import OrderedDict


req = urllib2.Request('http://www.petmd.com/pet-medication/acepromazine', headers={ 'User-Agent': 'Mozilla/5.0' })

url = urllib2.urlopen(req).read()
soup = BeautifulSoup(url, 'html.parser')

title = soup.title(text=True)
print title
stripped_title = ""
for char in title[0]:
    if char != '-':
        stripped_title += char
    else:
        break

stripped_title = stripped_title.strip
print stripped_title

article_body = soup.find('div', {'itemprop': 'articleBody'})
# print article_body

def h23_but_not_crap(tag):
    return tag.name == "h2" or tag.name == "h3" and tag.text != u"\xa0"

article_tags_list = article_body.find_all(h23_but_not_crap)
print article_tags_list

first_p = article_body.find('p')
print first_p.text, "<<< FIRST P"

article_tags_list_strings = []
for i in article_tags_list:
    article_tags_list_strings.append(str(i.text))
print article_tags_list_strings, "<<< ARE THESE STRINGS?"

article_body = first_p.text
split_article_body = article_body.split('\n')
print split_article_body, "<<< SPLIT ARTICLE BODY"
print

# NEED TO GET GENERAL DESCRIPTION TOO

# for i in range(len(article_tags_list)):
#     start_tag = article_tags_list[i]
#     try:
#         end_tag = article_tags_list[i+1]
#     except IndexError:
#         end_tag = soup.new_tag("h3", "")
#     content_list = []
#     next_tag = start_tag
#     for string in split_article_body:
#         if next_tag == end_tag.text:
#             break
#         # NEED TO DO SOMETHING SPECIFIC FOR SIDE EFFECTS & DRUG INTERACTIONS
#         else:
#             content_list.append(next_tag)
#             next_tag = next_tag.find_next(string=True)
#     print content_list, "<<<"

headers_index_list = []
for i in range(len(split_article_body)):
    if split_article_body[i] in article_tags_list_strings:
        headers_index_list.append(i)

print headers_index_list

petmd_dict = OrderedDict([])
for i in range(len(article_tags_list_strings)):
    if i < len(article_tags_list_strings)-1:
        petmd_dict[article_tags_list[i].text] = split_article_body[(headers_index_list[i]+1):headers_index_list[i+1]]
    else:
        petmd_dict[article_tags_list[i].text] = split_article_body[(headers_index_list[i]+1):]

print petmd_dict
print petmd_dict.keys()

# print 'len split bod',len(split_article_body),split_article_body

# for i in xrange(len(article_tags_list)):
#     start_tag = article_tags_list[i]
#     # print "PPP",start_tag.parent.name
#     try:
#         end_tag = article_tags_list[i+1]
#     except IndexError:
#         end_tag = soup.new_tag("h3", "")
#     content_list = []
#     next_tag = start_tag
#     #for string in split_article_body:
#     for ii in xrange(len(split_article_body)+80):
#         if next_tag == end_tag.text:
#             # print 'tag break', i, len(article_tags_list)
#             break
#         # NEED TO DO SOMETHING SPECIFIC FOR SIDE EFFECTS & DRUG INTERACTIONS
#         else:
#             # print "TTTT",[next_tag.text,next_tag.string,next_tag.name]
#             # print "TTT", next_tag in article_tags_list
#             content_list.append(next_tag)
#             next_tag = next_tag.find_next(string=True)

#     print content_list, "<<<"


# # THE CODE BELOW IS HARDCODED-- will try to create a loop instead to automate later.
# gen_desc_str = "General Description"
# general_description_tag = article_body.find("h2", string=gen_desc_str)
# print general_description_tag

# how_it_works_str = "How It Works"
# how_it_works_tag = article_body.find("h3", string=how_it_works_str)

# print how_it_works_tag

# side_effects_str = "Side Effects and Drug Reactions"
# side_effects_tag = article_body.find("h3", string=side_effects_str)

# interactions_str = "Acepromazine may react with these drugs:"
# interactions_tag = article_body.find("p", string=interactions_str)
# print interactions_tag

# missed_dose_str = "Missed Dose?"
# missed_dose_tag = article_body.find("h3", string=missed_dose_str)
# print missed_dose_tag


# article_body = str(article_body)
# split_article_body = article_body.split('\n')

# side_effects_list = []
# next_tag = side_effects_tag
# for string in split_article_body:
#     if next_tag == interactions_str:
#         break
#     else:
#         side_effects_list.append(next_tag)
#         next_tag = next_tag.find_next(string=True)
#         print "next tag is", next_tag
#         print type(next_tag)

# # print side_effects_list

# new_side = []
# for elem in side_effects_list:
#     if elem == side_effects_list[0] or elem == side_effects_list[1] or elem == u"\xa0" or elem == "\n":
#         print "found"
#     else:
#         new_side.append(elem)

# print new_side

# drug_interactions = []
# next_tag = interactions_tag
# for string in split_article_body:
#     drug_interactions.append(next_tag)
#     next_tag = next_tag.find_next(string=True)

# # print drug_interactions

# # print(soup.prettify())
