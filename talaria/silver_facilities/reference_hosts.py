"""Host lists for group F, source quality (spec #13, #15).

Reviewable data: add or remove a host in a pull request. A listed host matches
itself and any subdomain (`facebook.com` matches `m.facebook.com`). Lower-case,
no scheme, no `www.`.

The directory list started from the most common `source_urls` hosts on
2026-11-21: listings, aggregators, booking and insurance-network sites that list
many facilities. Encyclopaedias, news sites and journals are deliberately not
directories.
"""

# Hosts ending in one of these are government sources.
GOVERNMENT_SUFFIXES = [".gov.in", ".nic.in", ".gov"]

DIRECTORY_HOSTS = [
    "1mg.com",
    "5bestincity.com",
    "ambitionbox.com",
    "apollo247.com",
    "ayushmancardhospitals.com",
    "bajajfinservhealth.in",
    "bdir.in",
    "bharatibiz.com",
    "cardiologistindia.com",
    "cashlesshospitalindia.com",
    "chotu.com",
    "clinicspots.com",
    "crunchbase.com",
    "diagnosticcentres.in",
    "dnb.com",
    "docindia.org",
    "drlogy.com",
    "eka.care",
    "grotal.com",
    "healthfrog.in",
    "healthinsuranceindia.org",
    "hexahealth.com",
    "indiamart.com",
    "insurancedekho.com",
    "joonsquare.com",
    "justdial.com",
    "kivihealth.com",
    "latlong.net",
    "lybrate.com",
    "magicpin.in",
    "mapcarta.com",
    "mappls.com",
    "medicineindia.org",
    "medifee.com",
    "medindia.net",
    "mediyaar.com",
    "myhospitalnow.com",
    "myupchar.com",
    "onefivenine.com",
    "policybazaar.com",
    "policyx.com",
    "practo.com",
    "proceed.fit",
    "proptiger.com",
    "sehat.com",
    "skedoc.com",
    "sulekha.com",
    "tracxn.com",
    "tradeindia.com",
    "watchdoq.com",
    "whatclinic.com",
    "zaubacorp.com",
    "zoominfo.com",
]

SOCIAL_HOSTS = [
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "youtube.com",
]
