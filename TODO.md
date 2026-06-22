# DMRC PPE Tracking System - TODO

# Video upload processing speed fixes

- [ ] Reduce inference frequency for uploaded video jobs to speed up processing (increase skip_frames).
- [ ] Fix/avoid potential hang/slowdown in violation association by making association cheaper (remove O(N^2) IoU loop or bound comparisons).
- [ ] Add periodic debug logging of processed_frames / inference time so it’s obvious where time is spent.
- [ ] Add safeguards: if VideoWriter is failing, or if output grows, update job.output_path early.
- [ ] Run local test: upload a sample clip and confirm processed_frames increases and job completes.

# Build/Dev tooling fixes

- [ ] Add missing `lint` script so `npm run lint` does not fail during video upload/process flow.

