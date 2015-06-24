import requests
import random
import xml.dom.minidom
from lxml import etree
from threading import Thread
import hashlib
import logging

# create logger with 'spam_application'
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
# create file handler which logs even debug messages
fh = logging.FileHandler('/tmp/adstitch.log')
fh.setLevel(logging.DEBUG)
# create console handler with a higher log level
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
ch.setFormatter(formatter)
# add the handlers to the logger
logger.addHandler(fh)
logger.addHandler(ch)

'''
Simple script to generate a VMAP ad request and parse the response from Freewheel
'''

#nw
NETWORK = "375613"
#prof
# HbbTV Profile
PROFILE = "MSN_AU_HbbTV_Live"
# ios profile
#PROFILE = "MSN_AU_ios_Live"
#PROFILE = "MSN_AU_BC_Live"
# base URL
SERVER = "http://5bb3d.v.fwmrm.net/ad/g/1?"

# caid
# shortform
#asset = "3657904242001"
# longform
asset = "3654502947001"
asset = "3649633236001"

#csid
#section = "jumpin_web_episodes"
#SECTION = "music_general"
SECTION = "jumpin_hbbtv_general"

resp = "vmap1" #;module=DemoPlayer"

#slots = [0,589,1328,1500]

width = "1280"
height = "720"

ios_config = {
              "profile":"MSN_AU_ios_live",
              "section":"jumpin_ios",
              "ua":"Mozilla/5.0 (iPhone; CPU iPhone OS 6_0 like Mac OS X) AppleWebKit/536.26 (KHTML, like Gecko) Version/6.0 Mobile/10A5376e Safari/8536.25"
              }

android_config = {
              "profile":"MSN_AU_ios_live",
              "section":"jumpin_ios",
              "ua":""
              }

hbbtv_config = {
              "profile":"MSN_hbbtv_live",
              "section":"jumpin_ios",
              "ua":""
              }

web_flash_config = {
              "profile":"MSN_AU_as3_Live",
              "section":"jumpin_web_episodes",
              "ua":""
              }

web_html5_config = {
              "profile":"MSN_AU_BC_HTML5_Live",
              "section":"jumpin_web_episodes",
              "ua":""
              }


# http://hub.freewheel.tv/display/techdocs/Capabilities+in+Ad+Request
flags = "+emcr+slcb+fbad"

chrome_ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/37.0.2062.20 Safari/537.36"

headers = {
    'User-Agent': ios_config["ua"]
    }

'''
FW Example
http://demo.v.fwmrm.net/ad/g/1?flag=+emcr+slcb&nw=96749&prof=global-as3&csid=DemoSiteGroup.01&
caid=DemoVideoGroup.01&vdur=3000&resp=vast2&crtp=vast2s;module=DemoPlayer&feature=simpleAds;
slid=pre&tpos=0&ptgt=a&slau=preroll;slid=overlay&tpos=10&ptgt=a&slau=overlay;slid=display&ptgt=s&slau=display&w=728&h=90&flag=+cmpn;

'''

# Specify the UA which is also used by Freewheel for targeting
headers = {
           'User-Agent' : 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/36.0.1985.103 Safari/537.36'
           }


def ad_request(id, duration="60", profile=PROFILE, network=NETWORK):
    '''
    Makes a post to FW using params
    $network - 375613
    $profile - 375613:MSN_AU_BC_Live
    $site_section - 
    $media - 
    $random
    '''
    f = open('/Users/andrew/Desktop/workspace/AdaptivePlayout/adstitch/freewheel_post_template.xml','r')
    template = f.read()
    f.close()
    
    template = template.replace("$videoid",str(id))
    template = template.replace("$network",network)
    template = template.replace("$profile",profile)
    template = template.replace("$site_section","dma_news")
    template = template.replace("$duration",duration)
    
    fw_url = "http://5bb3d.v.fwmrm.net/ad/p/1?"
    
    resp = requests.post(fw_url, data=template, headers=headers)
    myxml = xml.dom.minidom.parseString(resp.text)
    
    # find if we have an errors section looks like this
    '''
    <errors>
    <error id='3' name='INVALID_ASSET_CUSTOM_ID' severity='WARN'>
      <context>37130581272001</context>
    </error>
  </errors>
    
    '''
    error = myxml.getElementsByTagName('error')
    if error:
        return "ERROR", error[0].attributes["name"].value
    return "OK", None #resp.text
    #return template

def gen_slots_string(slots):
    slot_string = "feature=simpleAds;"
    count = 1
    logger.debug("Slots " + str(slots))
    for slot in slots:
        logger.debug("Slot " + str(slot))
        if slot == 0:
            # pre roll, not could also just force this on all ads
            slot_string += ";slid=pre&tpos=0&ptgt=a&slau=preroll&tpcl=PREROLL"
        else:
            pass
            slot_string += ";slid=mid" + str(count) + "&tpos=" + str(slot) + "&ptgt=a&tpcl=MIDROLL&cpsq=" + str(count)
            count += 1
    # Add the post roll
    slot_string += ";slid=post&tpos=" + str(count + 1) + "&ptgt=a&slau=postroll&tpcl=POSTROLL"
            
    return slot_string

def get_tag(id, slots, duration, profile=PROFILE, network=NETWORK, section=SECTION):
    # Build the ad tag url
    slot_string = gen_slots_string(slots)
    # Generate random variables for the player
    #pvm
    pvrn = random.randint(0,100000000)
    #vprn
    vprn = random.randint(0,100000000)
    url = ("%snw=%s&prof=%s&csid=%s&caid=%s&vprn=%s&pvrn=%s&resp=%s&flag=%s&%s&w=%s&h=%s&vdur=%s" \
    %  (SERVER, network, profile, section, id, vprn, pvrn, resp, slot_string, flags, width, height, duration))
    logger.debug("Created FW tag: " + url)
    return url

def get_creative_vast(url, detail=None, vast_tag=None):
    '''
    
    This is what an Adap.tv error looks like
    <VAST version="2.0">
<Error></Error>
<Extensions>
<Extension type="adaptv_error">
<Error code="2">
<![CDATA[No ad could be found matching this request. ]]>
</Error>
</Extension>
</Extensions>
</VAST>
    '''
    logger.debug("Requesting from ad server: " + url)
    resp = requests.get(url,headers=headers)
    #logger.debug("Got from ad server: " + resp.text)
    logger.debug(resp.text)
    myxml = xml.dom.minidom.parseString(resp.text)
    inlines = myxml.getElementsByTagName('InLine')
    #logger.debug(vast_tag[0].firstChild.nodeValue)
    if detail is None:
        detail = {}
    creative = {}
    if vast_tag:
        detail["vast_tag"] = vast_tag[0].firstChild.nodeValue
    for inline in inlines:
        # TODO should check the multiple creatives and pick out the top bit rate
        mediafiles = inline.getElementsByTagName('MediaFile')
        
        detail = get_creative_details(inline)
        creative = mediafiles[0].firstChild.nodeValue
        if creative:
            print "Found creative: " + creative
    # Now check if we have a Wrapper
    wrappers = myxml.getElementsByTagName('Wrapper')
    for wrapper in wrappers:
        vast_tag = wrapper.getElementsByTagName('VASTAdTagURI')
        detail["VASTAdTagURI"] = vast_tag[0].firstChild.nodeValue
        logger.debug("Wrapper in a wrapper %s" % vast_tag[0].firstChild.nodeValue)
        creative = get_creative_vast(vast_tag[0].firstChild.nodeValue, detail=detail, vast_tag=vast_tag)
        detail["creative"] = creative
        logger.debug(creative)
        
    return detail

def get_creative_details(myxml):
    response = {}
    
    try:
        mediafiles = myxml.getElementsByTagName('MediaFile') 
        adSystem = myxml.getElementsByTagName('AdSystem')
        logger.debug("AdSystem: " + adSystem[0].firstChild.nodeValue)
        adTitle = myxml.getElementsByTagName('AdTitle')
        logger.debug("AdTitle: " + adTitle[0].firstChild.nodeValue)       
        creativeFile = mediafiles[0].firstChild.nodeValue
        
        # Also need to get mediaFile properties
        # <MediaFile bitrate="884" delivery="progressive" height="360" type="video/mp4" width="640"> 
        
        try:
            response["adSystem"] = adSystem[0].firstChild.nodeValue
        except:
            logger.warn("No ad system available")
            response["adSystem"] = None
        
        try:
            response["adTitle"] = adTitle[0].firstChild.nodeValue
        except:
            logger.warn("No ad system available")
            response["adTitle"] = None
        try:
            response["width"] = mediafiles[0].attributes["width"].value
        except:
            logger.warn("No ad width available")
            response["width"] = None
            
        try:
            response["height"] = mediafiles[0].attributes["height"].value
        except:
            logger.warn("No ad height available")
            response["height"] = None
        try:
            response["bitrate"] = mediafiles[0].attributes["bitrate"].value
        except:
            logger.warn("No ad bitrate available")
            response["bitrate"] = None
        try:
            response["url"] = creativeFile
        except:
            logger.warn("No ad url available")
            response["url"] = None
            
        logger.debug("Creative dimemsions: %sx%s" % (response["width"], response["height"]))  
        logger.debug("Creative bitrate: %s" % (response["bitrate"]))
    except:
        logger.error("Problem getting creative details for: " + str(mediafiles))
    
    return {"creative":response}

def get_mediafiles(myxml, url):
    '''
    Parse the VMAP response and get out the ads we want to ad in
    For these we need something like this
    adbreaks[
        adbreak : {"time": time, slots: [url]}
        ]
    
    TODO need to multi thread the retrieval of VAST data
    
    '''
    adbreaks = myxml.getElementsByTagName('vmap:AdBreak')
    adbreak_resp = []
    adbreak_resp.append({"adTag" : url})
    adbreak_resp.append(headers)
    creatives = []
    for adbreak in adbreaks:
        breakid = adbreak.attributes["breakId"].value
        timeOffset = adbreak.attributes["timeOffset"].value
        #print adbreak.toxml() 
        slots = []
        vastads = adbreak.getElementsByTagName('Ad')
        for ad in vastads:
            '''
            In the ads they are going to be of type Inline or Wrapper
            If it is Inline we should be able to get the creative here otherwise we need to retrieve the wrapper and parse
            '''
            print "Processing %s slot %s" % (breakid, ad.attributes["sequence"].value)
            # Now let's check for creatives
            inlines = ad.getElementsByTagName('InLine')
            wrappers = ad.getElementsByTagName('Wrapper')
            
            for inline in inlines:
                creatives.append({"creative":get_creative_details(inline)})
                mediafiles = inline.getElementsByTagName('MediaFile')  
                slots.append(get_creative_details(inline))
                
            for wrapper in wrappers:
                vast_tag = wrapper.getElementsByTagName('VASTAdTagURI') 
                creative = get_creative_vast(vast_tag[0].firstChild.nodeValue, vast_tag=vast_tag)
                slots.append(creative)
                #creative = ad.getElementsByTagName('Creatives')
     
        adbreak_resp.append({"adbreak" : {"breakid": breakid, "time": timeOffset, "slots": slots}})
    return adbreak_resp

def get_response(url):
    '''
    Makes the query to Freewheel to get the ad response
    Returns a minidom XML object
    '''
    logger.debug(url)
    fwresp = requests.get(url, headers=headers)
    #print fwresp.text
    
    myxml = xml.dom.minidom.parseString(fwresp.text)
    f = open("/tmp/vmap.xml","w")
    f.write(myxml.toprettyxml())
    f.close()
    return get_mediafiles(myxml, url)
    

    