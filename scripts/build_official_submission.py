"""Build a template-based submission with confirmed registration details.

PPTX edits use artifact-tool; PDF pages use its verified slide renders.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'output/organizer-template-build'
sys.path.insert(0, str(ROOT / '.local/submission-tools'))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--team-size', required=True, type=int)
    parser.add_argument('--basename', default='Samvaad360_Official_Submission')
    parser.add_argument('--native-verified', action='store_true', help='Use only after actual native trace is corroborated with stored results.')
    args = parser.parse_args()
    if args.team_size < 1:
        parser.error('Team size must be positive and confirmed by participant.')
    if not re.fullmatch(r'[A-Za-z0-9_-]+',args.basename):
        parser.error('Invalid output basename.')
    script = BUILD / 'build_official_submission.mjs'
    shutil.copyfile(ROOT / 'scripts/build_official_submission.mjs', script)
    subprocess.run([shutil.which('node'), str(script), str(ROOT), str(args.team_size),args.basename,'verified-native' if args.native_verified else 'unverified-native'], cwd=BUILD, check=True)
    qa = BUILD / 'final-preview' / args.basename
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    from PIL import Image
    from pypdf import PdfReader
    import fitz
    target = ROOT / 'submission' / (args.basename+'.pdf')
    pdf = canvas.Canvas(str(target), pagesize=(960,540), pageCompression=1)
    pdf.setTitle('Samvaad360 - Glacier Queries - Official Prototype Submission')
    pdf.setAuthor('Glacier Queries | Arunvpp')
    pdf.setSubject('Customer 360 and Next Best Action Engine - fictional lending prototype')
    for n in range(1,7):
        pdf.drawImage(ImageReader(str(qa / f'slide-{n:02}.png')),0,0,width=960,height=540)
        if n == 5:
            # Bounds checked against the actual 1440 x 810 artifact-tool render.
            # PDF coordinates start at the bottom of the page.
            pdf.linkURL('https://samvaad360.streamlit.app/',(44,191,370,216),relative=0,thickness=0)
            pdf.linkURL('https://github.com/Cherie05/samvaad360',(44,127,438,152),relative=0,thickness=0)
        pdf.showPage()
    pdf.save()
    assert len(PdfReader(target).pages)==6
    assert target.stat().st_size < 5_000_000
    with fitz.open(target) as doc:
        for n,page in enumerate(doc,1):
            page.get_pixmap(matrix=fitz.Matrix(1.5,1.5)).save(str(qa / f'pdf-page-{n:02}.png'))
    pptx=ROOT / 'submission' / (args.basename+'.pptx')
    inspect_dump=Path(str(pptx)+'.inspect.ndjson')
    if inspect_dump.exists():
        inspect_dump.replace(BUILD / inspect_dump.name)
    with ZipFile(pptx) as archive:
        xml='\n'.join(archive.read(n).decode('utf-8') for n in archive.namelist() if n.endswith(('.xml','.rels')))
        for pattern in (r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',r'gh[pousr]_[A-Za-z0-9_]{20,}',r'github_pat_[A-Za-z0-9_]{20,}'):
            assert not re.search(pattern,xml), 'Credential pattern found; inspect privately.'
        assert xml.count('[Sources]')==6
        assert 'Glacier Queries' in xml and 'Arunvpp' in xml
        assert 'Submission Guidelines:' not in xml
    sheet=Image.new('RGB',(980,860),'#E7EBEF')
    for i in range(6):
        image=Image.open(qa / f'slide-{i+1:02}.png').convert('RGB')
        image.thumbnail((480,270))
        sheet.paste(image,(10+(i%2)*490,10+(i//2)*280))
    sheet.save(qa / 'contact-sheet.png')
    data={'basename':args.basename,'team_name':'Glacier Queries','team_leader':'Arunvpp','team_size':args.team_size,'template':'Participant-provided official PPTX','slide_count':6,'pdf_bytes':target.stat().st_size,'pdf_under_5mb':True,'pptx_bytes':pptx.stat().st_size,'pdf_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'pptx_sha256':hashlib.sha256(pptx.read_bytes()).hexdigest(),'native_coco_workflow_verified':args.native_verified,'native_coco_video_verified':False,'portal_submitted':False,'visual_qa':'Pending individual inspection.'}
    (BUILD / (args.basename+'-result.json')).write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(data,indent=2))

if __name__=='__main__':
    main()
