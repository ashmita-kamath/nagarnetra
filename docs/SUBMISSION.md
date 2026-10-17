# Unstop submission - copy-paste answers

## Project title

NagarNetra: AI-Powered Civic Issue Reporting with Open-Source YOLO11 and Cloudinary

## Problem Statement and Solution Brief

Problem: Indian cities receive thousands of civic complaints as scattered calls, tweets and WhatsApp photos. Authorities cannot tell a dangerous crater from a minor crack, the same pothole is filed dozens of times as separate tickets, and citizens never see whether anything was fixed, so they stop reporting.

Solution: NagarNetra is a no-install web app. A citizen snaps a photo and drops a location. An open-weight YOLO11 model, fine-tuned on an open pothole dataset and served via ONNX Runtime, detects the damage and computes a 0-100 severity score from damage area, count and confidence. Reports within 25 m of an existing open issue are merged, so repeats become a crowd signal instead of duplicates. Priority combines severity, citizen reports and waiting time into a live "fix first" map for the municipality. When an issue is repaired, an "after" photo closes the loop with a public before/after image.

Cloudinary powers the media layer: automatic face blurring on every public image for privacy, AI smart-crop thumbnails (g_auto), f_auto/q_auto delivery for slow mobile networks, on-the-fly shareable severity cards using text overlays, before/after composites using image layers, and tags plus context metadata that make the media library a searchable issue archive.

Stack: FastAPI, YOLO11 + ONNX Runtime, Cloudinary, Supabase Postgres, Leaflet + OpenStreetMap. Fully open source (AGPL-3.0), with our build journey documented on Notion.

## GitHub repository URL

https://github.com/YOUR-USERNAME/nagarnetra

## Notion documentation URL

(your published Notion page link)

## Live demo URL

https://nagarnetra.onrender.com (replace with your Render URL)

## How have you used Cloudinary?

Yes
