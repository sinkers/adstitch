'''
Script to get a video file and break into segments for stitching ads in

'''

import sys
import json
from datetime import datetime
import requests
import freewheel
import os
from threading import Thread
import hashlib
import time
import subprocess
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

TMP = "/tmp/"
# Add the path to the Brightcove Plus library
# https://bitbucket.org/ajsinclair/bcplus
sys.path.insert(0, 'path to bcplus')
import brightcove
APIKEY = "ENTER BRIGHTCOVE KEY HERE"
FFMPEG_CMD = "/usr/local/bin/ffmpeg"
FFPROBE = "/usr/local/bin/ffprobe"
MP4FRAGMENT = "/Users/andrew/Desktop/workspace/hbbtv/Bento4-SDK-1-3-5-541.universal-apple-macosx/bin/Release/mp4fragment"
MP4DASH = "/Users/andrew/Desktop/workspace/hbbtv/Bento4-SDK-1-3-5-541.universal-apple-macosx/utils/mp4-dash.py"
DASHOUT = "/Users/andrew/Desktop/workspace/hbbtv/output/"
DASHURL = "http://localhost/workspace/hbbtv/output/"

size = "640x360"

def get_bc_video(id):
    '''
    BC returns cuepoints in milliseconds
    Duration/length is in millisceonds
    '''
    video_url = ""
    result = brightcove.find_video_by_id(APIKEY, id)
    data =  json.loads(result)
    # Small bit of logic to get a video
    logger.debug("Data: " + json.dumps(data, indent=4))
    try:
        video_url = data["FLVURL"]
    except:
        logger.debug("No FLVURL found for " + id)
        video_url = None
        
    if video_url == None or (os.path.splitext(video_url)[1] == "mp4"):
        video_url = data["FLVFullLength"]["url"]
    logger.debug("Got BC video " + video_url)
    cuepoints = data["cuePoints"]
    length = data["length"]
    return video_url, cuepoints, length

def get_file_info(url):
    cmd = FFPROBE + " -print_format json -show_format -show_streams " + url
    p = subprocess.Popen(cmd.split(" "), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    text = p.stdout.read()
    retcode = p.wait()
    return json.loads(text)

def create_bc_cues(cuepoints,length):
    '''
    Simple function that takes a list of cuepoints from brightcove and formats them to our internal format
    Which is simply an order list of times
    
    Sample cuepoints
    {u'name': u'Pre-roll', u'videoId': 1799629325001, u'typeEnum': u'AD', u'forceStop': False, u'time': 0.0, u'type': 0, u'id': 1799356691001, u'metadata': None}
    {u'name': u'midroll1', u'videoId': 1799629325001, u'typeEnum': u'AD', u'forceStop': False, u'time': 572015.0, u'type': 0, u'id': 1799356692001, u'metadata': u'slots=5'}
    {u'name': u'midroll2', u'videoId': 1799629325001, u'typeEnum': u'AD', u'forceStop': False, u'time': 1117005.0, u'type': 0, u'id': 1799356693001, u'metadata': u'slots=5'}
    {u'name': u'Post-roll', u'videoId': 1799629325001, u'typeEnum': u'AD', u'forceStop': False, u'time': 1542400.0, u'type': 0, u'id': 1799356690001, u'metadata': None}
    '''
    newcues = sorted(cuepoints, key=lambda k: k['time'])
    cues = []
    for cue in newcues:
        # only add mid-rolls here, that is don't add a post-roll
        #print cue
        # (not int(cue["time"]) == int(length)) or 
        #if not int(cue["time"] == 0):
        cues.append(int(cue["time"]))
    logger.debug("Got cues " + str(cues))    
    return cues

def download_file(url):
    '''
    Just downloads a file
    Should add a check for local cached version
    '''
    m = hashlib.md5()
    m.update(url)
    local_filename = TMP + m.hexdigest() #url.split('/')[-1]
    if (os.path.exists(local_filename)):
        logger.info("File exists skipping download " + local_filename)
    else:
    # NOTE the stream=True parameter
        logger.debug("Downloading " + url)
        r = requests.get(url, stream=True, verify=False)
        with open(local_filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024): 
                if chunk: # filter out keep-alive new chunks
                    f.write(chunk)
                    f.flush()
    return local_filename
     
def create_splice_strings(cuepoints, infile, length):
    '''
    Generates an ffmpeg string for splicing a video into .ts segments
    Sample ffmpeg -i 67420370.mp4 -bsf h264_mp4toannexb -ss 00:01:00 -t 60 -c:v copy -c:a copy splice/67420370_seg2.ts
    Need to know the start time which is the time of the cuepoint and then the duration which is the time to the next cuepoint
    
    Some things to note about frame splicing
    When cutting 2 files to get them to join exactly back together we need to go with the exact frame that the slice was made
    e.g. a 25fps file has a frame every 0.04 seconds (40 ms)
    The cut will usually happen at a key frame so we also need to make sure we have a keyframe at boundaries of cuts
    It also appears that when ffmpeg cuts a compressed video it does so at a P frame boundary
    
    '''
    splice_commands = []
    splice_files = []
    current = 0
    for cue in cuepoints:
        print cue, length
        if ((current + 1) < len(cuepoints)) and (not cue == length):
            start = str(cue/1000)
            finish = str(cuepoints[current + 1]/1000)
            if not start == finish:
                outfile = "%s_%s.ts" % (infile, current)
                logger.debug("Split for %s to %s" % (start, finish))
                params = {"start":start, "finish":finish, "infile":infile, "outfile":outfile, "ffmpeg":FFMPEG_CMD}
                splice_commands.append("%(ffmpeg)s -y -i %(infile)s -bsf h264_mp4toannexb "\
"-force_key_frames 'expr:gte(t,n_forced*2)' -b:v 1000k -b:a 64k -aspect 1.7777 -r 25 -g 25 -ss %(start)s -t %(finish)s -c:v libx264 "\
"-c:a libfdk_aac -ar 44100 %(outfile)s" % params)
                splice_files.append(outfile)
                current += 1
        else:
            # There is only one file
            outfile = "%s.ts" % (infile)
            params = {"infile":infile, "outfile":outfile, "ffmpeg":FFMPEG_CMD}
            splice_commands.append("%(ffmpeg)s -y -i %(infile)s -aspect 1.7777 -bsf h264_mp4toannexb "\
"-force_key_frames 'expr:gte(t,n_forced*2)' -c:v libx264 "\
"-c:a libfdk_aac -b:v 1000k -b:a 64k -ar 44100 %(outfile)s" % params)
            splice_files.append(outfile)
    return splice_commands, splice_files

def encode_ad(url):
    '''
    Downloads an ad and transcodes to a compatible splice format
    '''
    m = hashlib.md5()
    m.update(url)
    outfile = TMP + m.hexdigest() + ".ts"
    print "**Process ad %s" % outfile
    
    infile = download_file(url)
    
    
    params = {"ffmpeg":FFMPEG_CMD, "infile":infile, "outfile":outfile, "size":size}
    if (os.path.exists(outfile)):
        print "Ad already encoded, skipping"
    else:
        # TODO copy all input settings from the source other than just size e.g. audio rate, bitrate etc
        ffcmd = "%(ffmpeg)s -y -i %(infile)s -bsf h264_mp4toannexb -b:v 1000k -b:a 64k -r 25 -g 25 -c:v libx264 -c:a libfdk_aac -ar 44100 -s %(size)s -profile:v main %(outfile)s"\
            % params
        print ffcmd
        p = subprocess.Popen(ffcmd.split(" "), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        text = p.stdout.read()
        retcode = p.wait()
        #os.system(ffcmd)
    
    return outfile

def encode_file(url, ffcmd):
    '''
    Downloads an ad and transcodes to a compatible splice format
    '''
    infile = download_file(url)
    outfile = TMP + url.split('/')[-1] + ".ts"
    params = {"ffmpeg":FFMPEG_CMD, "infile":infile, "outfile":outfile, "size":size}
    if (os.path.exists(outfile)):
        print "File already encoded, skipping"
    else:
        ffcmd = "%(ffmpeg)s -i %(infile)s -c:v libx264 -c:a libfdk_aac -s %(size)s -preset fast %(outfile)s"\
            % params
        logger.debug("Encode file: " + ffcmd)
        p = subprocess.Popen(ffcmd.split(" "), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        text = p.stdout.read()
        retcode = p.wait()
        #os.system(ffcmd)
    
    return outfile

def stitch_video(videos):
    '''
    Takes a list of spliced source videos and a list of ads to stitch in for each ad break
    '''
    
    m = hashlib.md5()
    output_string = ""
    concat_string = "concat:"
    for video in videos:
        output_string += "file " + video + "\n"
        concat_string += video + "|"
        m.update(video)
    concat_string = concat_string[:-1]
    
    id = m.hexdigest()
    output = TMP + id + ".mp4"
    
    tmpfile = TMP + "splice_" + id + ".txt"
    if not os.path.exists(output):
        f = open(tmpfile,'w')
        f.write(output_string)
        f.close
        # Provide some time for file to write to disk
        #time.sleep(10)
        params = {"ffmpeg":FFMPEG_CMD, "tmpfile": tmpfile, "output":output, "concat_string":concat_string}
        #ffcmd = "%(ffmpeg)s -y -f concat -i %(tmpfile)s -c copy -bsf:a aac_adtstoasc %(output)s" % params
        ffcmd = "%(ffmpeg)s -y -i %(concat_string)s -c copy -bsf:a aac_adtstoasc %(output)s" % params
        logger.debug("Stitch video: " + ffcmd)
        p = subprocess.Popen(ffcmd.split(" "), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        text = p.stdout.read()
        retcode = p.wait()
    
    return output
    
def make_dash(file):
    basename = os.path.basename(file)
    logger.debug("Dashifying " + file)
    fileName, fileExtension = os.path.splitext(os.path.basename(file))
    output = os.path.join(TMP,basename + "_frag.mp4")
    cmd = [MP4FRAGMENT, file,  output]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    text = p.stdout.read()
    retcode = p.wait()
    
    dashcmd = [MP4DASH, "-f", "--use-segment-timeline", output, "-o", os.path.join(DASHOUT,fileName), "-m", "manifest.mpd", "--use-segment-list"]
    logger.debug("".join(dashcmd))
    p = subprocess.Popen(dashcmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    text = p.stdout.read()
    logger.debug(text)
    retcode = p.wait()
    
    dashed_url = DASHURL + fileName + "/manifest.mpd"
    logger.info("Generated dashed url: " + dashed_url)
    return dashed_url
    
def stitch_mp4(video, vast):
    video_url = video
    #preroll only
    cuepoints = [0]
    
    local_source = download_file(video_url)
    fileinfo = get_file_info(local_source)
    size = str(fileinfo["streams"][0]["width"]) + "x" + str(fileinfo["streams"][0]["height"])
    fps = fileinfo["streams"][0]["r_frame_rate"]
    bitrate = fileinfo["streams"][0]["bit_rate"]
    length = fileinfo["streams"][0]["duration"]
    
    splice_commands, splice_files = create_splice_strings(cuepoints, local_source, length)
    print splice_commands

def stitch(id):
    
    logger.info("Stitching for asset: " + id)
    video_url, cuepoints, length = get_bc_video(id)
    
    # TODO only need to pull down the file info if we haven't downloaded the file
    # We should match the resolution, aspect ration, fps and bitrate
    fileinfo = get_file_info(video_url)
    # TODO this assumes the first stream is the video stream so need to check it is
    # TODO create a new meta extraction function
    size = str(fileinfo["streams"][0]["width"]) + "x" + str(fileinfo["streams"][0]["height"])
    fps = fileinfo["streams"][0]["r_frame_rate"]
    bitrate = fileinfo["streams"][0]["bit_rate"]
    
    # Download
    local_source = download_file(video_url)
    mycues = create_bc_cues(cuepoints, length)
    logger.debug(str(mycues))
    splice_commands, splice_files = create_splice_strings(mycues, local_source, length)
    
    # TODO this could be tidied a bit to move files and commands into a dict
    for idx, val in enumerate(splice_files):
        print "Check " + val
        if not os.path.exists(val):
            logger.debug(splice_commands[idx])
            p = subprocess.Popen(splice_commands[idx].split(" "), stdout=subprocess.PIPE)
            text = p.stdout.read()
            #retcode = p.wait()
    
    if len(mycues) == 1:
        fw_url = freewheel.get_tag(id, mycues, length / 1000)
    else:
        # Drop the post roll as we will add it? TODO check this out
        fw_url = freewheel.get_tag(id, mycues[:-1], length / 1000)
        
    adbreaks = freewheel.get_response(fw_url)
    #print adbreaks
    break_count = 0
    
    encode_params= []
    logger.debug(json.dumps(adbreaks))
    for adbreak in adbreaks:
        logger.debug(json.dumps(adbreak))
        
        if "adbreak" in adbreak:
            logger.info("Adbreak: " + adbreak["adbreak"]["breakid"])
            # Check for pre or post roll status
            if (adbreak["adbreak"]["breakid"] == "pre"):
                logger.debug("preroll slot")
                try:
                    encode_params.append(encode_ad(adbreak["adbreak"]["slots"][0]["creative"]["url"]))
                except:
                    pass
            elif (adbreak["adbreak"]["breakid"] == "post"):
                logger.debug("postroll slot")
                logger.debug("Splice files length: " + str(len(splice_files)))
                
                try:
                    if len(splice_files) > 0:
                        encode_params.append(splice_files[len(splice_files) - 1])
                    else:
                        encode_params.append(splice_files[len(splice_files)])
                    encode_params.append(encode_ad(adbreak["adbreak"]["slots"][0]))
                except:
                    pass
            else:
                try:
                    logger.debug("Video source: " + splice_files[break_count])
                    encode_params.append(splice_files[break_count])
                    for slot in adbreak["adbreak"]["slots"]:
                        if slot:
                            encode_params.append(encode_ad(slot))
                    break_count += 1
                except:
                    logger.error("Problem with break")
                    
                # Check for the last slot
                logger.debyg("Break count: break_count")
    
    for encode_file in encode_params:
        logger.debug("encode file: " + encode_file)
    
    stitched_video = stitch_video(encode_params)
    os.system("open " + stitched_video)
    return make_dash(stitched_video)
    #print "Finished"


# Yu gi goh: 3663622563001
# The voice; 3600304550001
# Hot seat 3669299593001
# Manspace
#stitch("3663655520001")


