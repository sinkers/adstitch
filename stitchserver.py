from flask import Flask, redirect, request
import adstitch
import freewheel
import json

app = Flask(__name__)

@app.route('/s/<id>')
def stitch(id):
    return redirect("http://localhost/workspace/hbbtv/dash.js/?url=" + adstitch.stitch(id))

@app.route('/s/mp4/')
def stitch_mp4_preroll(id):
    '''
    Simplified stich server that takes an input file and a vast tag
    '''
    video = request.args.get("video")
    vast = request.args.get("vast")
    
    return "OK"

@app.route('/vast/<url>')
def get_vast(url):
    url = request.args.get("url",None)
    return json.dumps(freewheel.get_creative_vast(url))

@app.route('/test')
def test():
    return "OK"

@app.route('/debug/<videoid>')
def ad_debug(videoid):
    profile = request.args.get("profile",None)
    tag = freewheel.get_tag(videoid, [0,90,180], 500)
    #return tag
    return json.dumps(freewheel.get_response(tag))

if __name__ == '__main__':
    app.run(host='0.0.0.0',port=5013,debug=True)