"""Combine the participant's actual native CoCo recording with real hosted UI.

All audio is removed. The source recordings are preserved. Only complete
website chapter sections are selected; no terminal output is generated/replayed.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.local/submission-tools'))
import imageio_ffmpeg

def media_info(ffmpeg,file):
    check=subprocess.run([ffmpeg,'-i',str(file)],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)
    match=re.search(r'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)',check.stderr)
    if not match: raise RuntimeError('MEDIA_DURATION_UNREADABLE')
    h,m,s=map(float,match.groups())
    return {'seconds':h*3600+m*60+s,'has_audio_stream':'Audio:' in check.stderr,'video_stream':next((x.strip() for x in check.stderr.splitlines() if 'Video:' in x),None)}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-recording',required=True,type=Path)
    args=parser.parse_args()
    native=args.native_recording.resolve(strict=True)
    web=ROOT/'submission/Samvaad360_Demo.mp4'
    folder=ROOT/'output/submission-coco-video'
    folder.mkdir(parents=True,exist_ok=True)
    ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
    source=media_info(ffmpeg,native)
    if not 30<=source['seconds']<=125:
        raise RuntimeError('Review duration and trim native waits explicitly before combining.')
    original=json.loads((ROOT/'output/submission-video/result.json').read_text(encoding='utf-8'))
    selected=[1,3,4,5,7,8,9]
    chapters=[original['chapters'][i-1] for i in selected]
    website_speed=original['playback_speed']
    expected=source['seconds']+sum((x['end']-x['start'])/website_speed for x in chapters)
    if not 180<=expected<=300: raise RuntimeError('VIDEO_OUTSIDE_3_TO_5_MINUTES')
    shutil.copyfile(Path('C:/Windows/Fonts/segoeuib.ttf'),folder/'label-font.ttf')
    (folder/'native-label.txt').write_text('Samvaad360 / Glacier Queries | Actual CoCo CLI: three skills + safe idempotent replay',encoding='utf-8')
    (folder/'website-label.txt').write_text('Samvaad360 / Glacier Queries | Public website UI | Fictional Snowflake data | Recorded at 1.4x',encoding='utf-8')
    transform="scale=1920:1032:force_original_aspect_ratio=decrease:force_divisible_by=2,pad=1920:1080:(ow-iw)/2:48+(1032-ih)/2:color=0x143D35,setsar=1,fps=30"
    label="drawtext=fontfile='label-font.ttf':textfile='{file}':x=24:y=9:fontsize=27:fontcolor=white"
    pieces=[f"[0:v]trim=start=0:end={source['seconds']},setpts=PTS-STARTPTS,{transform},{label.format(file='native-label.txt')}[v0]"]
    pieces.append('[1:v]split='+str(len(chapters))+''.join(f'[s{i}]' for i in range(1,len(chapters)+1)))
    for i,ch in enumerate(chapters,1):
        start,end=ch['start']/website_speed,ch['end']/website_speed
        pieces.append(f"[s{i}]trim=start={start:.6f}:end={end:.6f},setpts=PTS-STARTPTS,{transform},{label.format(file='website-label.txt')}[v{i}]")
    pieces.append(''.join(f'[v{i}]' for i in range(len(chapters)+1))+f'concat=n={len(chapters)+1}:v=1:a=0[v]')
    filter_file=folder/'combine.fffilter'
    filter_file.write_text(';\n'.join(pieces),encoding='utf-8')
    output=ROOT/'submission/Samvaad360_CoCo_Submission.mp4'
    command=[ffmpeg,'-y','-i',str(native),'-i',str(web),'-filter_complex_script',str(filter_file),'-map','[v]','-an','-c:v','libx264','-preset','medium','-crf','21','-pix_fmt','yuv420p','-movflags','+faststart','-metadata','title=Samvaad360 | Glacier Queries | CoCo CLI and public UI','-metadata','comment=Actual native CoCo recording with an idempotent simulated replay; actual public UI footage. No audio. Fictional data. No real telephone calls.','-progress','pipe:1','-nostats',str(output)]
    # FFmpeg input metadata may exceed a pipe buffer before progress starts.
    # Write stderr directly to a private log so encoding cannot deadlock.
    with (folder/'encode-log.txt').open('w',encoding='utf-8') as error_log:
        process=subprocess.Popen(command,cwd=folder,stdout=subprocess.PIPE,stderr=error_log,text=True,encoding='utf-8',errors='replace')
        while True:
            row=process.stdout.readline()
            if not row and process.poll() is not None: break
            if row.startswith('out_time='): print(row.strip(),flush=True)
        if process.wait()!=0:
            raise RuntimeError('VIDEO_ENCODING_FAILED; inspect private encode-log.txt.')
    final=media_info(ffmpeg,output)
    assert 180<=final['seconds']<=300 and final['has_audio_stream'] is False
    report={'created_at_utc':datetime.now(timezone.utc).isoformat(),'media':str(output.relative_to(ROOT)),'seconds':final['seconds'],'width':1920,'height':1080,'has_audio_stream':False,'audio_removed':True,'native_source_seconds':source['seconds'],'native_playback_speed':1.0,'native_source_sha256':hashlib.sha256(native.read_bytes()).hexdigest(),'native_segment':'Actual participant-recorded CoCo prompt, tool processing, evidence/recommendation/status/runner output; idempotent replay of previously completed callback.','website_chapters':selected,'website_playback_speed':website_speed,'actual_hosted_website_recording':True,'real_calls_placed':False,'financial_changes_performed':False,'bytes':output.stat().st_size,'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'duration_requirement_verified':True,'visual_qa':'Pending full motion and frame review.','public_link_verified':False}
    (folder/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
