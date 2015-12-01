================
Companion Care
================

General Description
====================

**Pet Health in Real Time.**

CompanionCare is an app that helps conscientious pet partners manage the care of pets in need. Aging pets and pets with chronic health conditions often need to see many different vets and take many medications. Using a custom-scraped database of pet medications, CompanionCare tracks your pets' prescriptions — even sending responsive SMS alerts to keep you on top of doses, providing information on what to do if you miss a pill, and tracking prescribing vets to help you reach out when you need to. CompanionCare also helps document your pets’ lives in sickness and in health with photo uploads and lets you see an overview of the healthcare for all your pets with custom data visualizations.

Technology Stack & APIs
========================

**Backend:** Python, Flask, PostgreSQL, SQLAlchemy, BeautifulSoup4, Amazon S3, Twilio, Multiprocessing

**Frontend:** JavaScript, jQuery, AJAX, D3.js, Chart.js, Jinja2, Bootstrap, HTML, CSS

Selected Features
========================
-Storing and retrieving data from *PostgreSQL* across 12 integrated tables
-Custom webcrawler and webscraper using *BeautifulSoup4*
-Real-time, reponsive SMS alerts asynchronously by using Python's *Multiprocessing* library to create child daemonic processes and the *Twilio API* to send and retrieve SMS text alerts containing information stored in the database, with an algorithm to automatically schedule successive text alerts based on user response
-Display of Alert Response History data within a user-selected period of time using *Chart.js*
-Display of key relationships of essential information enabling the user to more easily see what data is missing, which alerts have and have not yet been scheduled, and a status on scheduled alerts
-Custom API to enable easy access for other developers interested in using the scraped pet medications data
-Photo upload using *Amazon S3*
-Responsive and mobile-friendly front-end using *Bootstrap, Jinja2, HTML,* and *CSS*
-*AJAX* and *jQuery* basically everywhere!  Seriously, lots of dynamically generated modals.
