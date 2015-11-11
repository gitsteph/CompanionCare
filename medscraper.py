from bs4 import BeautifulSoup
import urllib2
import re


req = urllib2.Request('http://www.petmd.com/pet-medication/acepromazine', headers={ 'User-Agent': 'Mozilla/5.0' })

url = urllib2.urlopen(req).read()
soup = BeautifulSoup(url, 'html.parser')

title = soup.title(text=True)
stripped_title = ""
for char in title[0]:
    if char != '-':
        stripped_title += char
    else:
        break

stripped_title = stripped_title.strip
print stripped_title

article_body = soup.find('div', {'itemprop': 'articleBody'})
print article_body

# THE CODE BELOW IS HARDCODED-- will try to create a loop instead to automate later.
gen_desc_str = "General Description"
general_description_tag = article_body.find("h2", string=gen_desc_str)
print general_description_tag

how_it_works_str = "How It Works"
how_it_works_tag = article_body.find("h3", string=how_it_works_str)

print how_it_works_tag

side_effects_str = "Side Effects and Drug Reactions"
side_effects_tag = article_body.find("h3", string=side_effects_str)

interactions_str = "Acepromazine may react with these drugs:"
interactions_tag = article_body.find("p", string=interactions_str)
print interactions_tag

missed_dose_str = "Missed Dose?"
missed_dose_tag = article_body.find("h3", string=missed_dose_str)
print missed_dose_tag


article_body = str(article_body)
split_article_body = article_body.split('\n')

side_effects_list = []
next_tag = side_effects_tag
for string in split_article_body:
    if next_tag == interactions_str:
        break
    else:
        side_effects_list.append(next_tag)
        next_tag = next_tag.find_next(string=True)
        print "next tag is", next_tag
        print type(next_tag)

print side_effects_list

drug_interactions = []
next_tag = interactions_tag
for string in split_article_body:
    drug_interactions.append(next_tag)
    next_tag = next_tag.find_next(string=True)

print drug_interactions

missed_dose = []
next_tag = missed_dose_tag
for string in split_article_body:
    if next_tag == side_effects_str:
        break
    else:
        missed_dose.append(next_tag)
        next_tag = next_tag.find_next(string=True)

print missed_dose


# THIS GETS ALL UL STUFF THOUGH, NOT JUST SIDE EFFECTS.  NEED A WAY TO SAY BETWEEN PTS.
# print article_body.select("p ul li")
# print(soup.prettify())
