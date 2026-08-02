#!/bin/bash
# make-slides.sh — regenerate the four stills build-video.sh uses.
# build-audio.sh wipes out/, so run this (and fit-to-audio.py) after it.
set -euo pipefail
cd "$(dirname "$0")"
FF=${FF:-/opt/homebrew/opt/ffmpeg@7/bin/ffmpeg}
B="fontfile='/System/Library/Fonts/Supplemental/Arial Bold.ttf'"
H="fontfile=/System/Library/Fonts/Helvetica.ttc"
bg() { "$FF" -y -v error -f lavfi -i color=c=0x0e131f:s=1920x1080 -frames:v 1 -vf "$1" "$2"; }

bg "drawtext=${B}:text='Recall':fontsize=170:fontcolor=0xf2f5fa:x=(w-text_w)/2:y=310,\
drawtext=${H}:text='An on-call agent whose memory is CockroachDB':fontsize=52:fontcolor=0xaebace:x=(w-text_w)/2:y=540,\
drawtext=${H}:text='CockroachDB x AWS Hackathon - Build with Agentic Memory':fontsize=34:fontcolor=0x67748c:x=(w-text_w)/2:y=640,\
drawtext=${H}:text='github.com/gmassello/recall':fontsize=34:fontcolor=0x5f8dff:x=(w-text_w)/2:y=790" out/slide.png

bg "drawtext=${B}:text='CockroachDB':fontsize=110:fontcolor=0xf2f5fa:x=(w-text_w)/2:y=250,\
drawtext=${H}:text='Distributed vector indexing - 1024-dim semantic recall':fontsize=44:fontcolor=0xaebace:x=(w-text_w)/2:y=480,\
drawtext=${H}:text='Cloud Managed MCP Server - the live read path':fontsize=44:fontcolor=0xaebace:x=(w-text_w)/2:y=570,\
drawtext=${H}:text='One database for the vectors and the transactions':fontsize=44:fontcolor=0x5f8dff:x=(w-text_w)/2:y=690" out/slide-crdb.png

bg "drawtext=${B}:text='AWS':fontsize=110:fontcolor=0xf2f5fa:x=(w-text_w)/2:y=250,\
drawtext=${H}:text='Lambda with response streaming - the serverless agent':fontsize=44:fontcolor=0xaebace:x=(w-text_w)/2:y=480,\
drawtext=${H}:text='S3 + CloudFront - the frontend':fontsize=44:fontcolor=0xaebace:x=(w-text_w)/2:y=570,\
drawtext=${H}:text='Deployed from GitHub Actions via OIDC':fontsize=44:fontcolor=0x5f8dff:x=(w-text_w)/2:y=690" out/slide-aws.png

bg "drawtext=${B}:text='Recall':fontsize=150:fontcolor=0xf2f5fa:x=(w-text_w)/2:y=330,\
drawtext=${H}:text='demo - d2n13wfb8jv9v.cloudfront.net':fontsize=42:fontcolor=0x5f8dff:x=(w-text_w)/2:y=560,\
drawtext=${H}:text='code - github.com/gmassello/recall':fontsize=42:fontcolor=0x5f8dff:x=(w-text_w)/2:y=640,\
drawtext=${H}:text='CockroachDB x AWS Hackathon - Build with Agentic Memory':fontsize=32:fontcolor=0x67748c:x=(w-text_w)/2:y=780" out/slide-close.png
echo "wrote out/slide.png slide-crdb.png slide-aws.png slide-close.png"
