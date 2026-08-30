# Data and licensing boundaries

This document records inspected terms and repository policy; it is not legal advice.

## StructAgent

Original code in this repository is MIT-licensed to Tony Kwok and Billy Zhao. That
license does not cover third-party source, models, datasets, trademarks, or other assets.
StructureML is an independent research initiative and is not currently incorporated.

## Datasets

- [RelBench](https://github.com/snap-stanford/relbench) source is MIT-licensed. The
  fixture schema was checked against RelBench, but no RelBench package or data is bundled
  or relicensed by this repository.
- The `rel-hm` catalog names fields from the H&M benchmark schema. H&M competition data
  has separate [Kaggle competition terms](https://www.kaggle.com/competitions/h-and-m-personalized-fashion-recommendations/rules)
  and is never bundled or redistributed by this repository.
- A project decision recorded on 2026-08-30 permits the
  `stanford-star/relbench-v1` revision
  `d8e976fd0a4b78877204bc8dfbcfc9a9f7f48600` for private research and hackathon
  demonstration only. The opt-in staging command downloads checksum-pinned files into the
  ignored `.artifacts/` cache. Downloaded inputs, derived labels, and parity results remain
  ignored local artifacts or private ephemeral Daytona files. This is a project use decision,
  not a legal conclusion about broader rights.
- Amazon source data and any hosted preprocessed snapshots remain external and require
  their own provenance and terms review before execution.

## RT-J

Inspection on 2026-08-30 found:

- [RT-J model assets](https://huggingface.co/stanford-star/rt-j) include separate
  classification and regression checkpoints and declare CC BY-NC-SA 4.0;
- the `main` revision `455df27c1458e093eac00133d5bbf41a8263a2e3` of the
  [Relational Transformer source repository](https://github.com/stanford-star/relational-transformer)
  had no root `LICENSE` file; and
- public availability alone does not grant this project commercial source-code rights.

Therefore this scaffold does not depend on, vendor, download, execute, redistribute, or
deploy RT-J. Commercial integration remains blocked until the intended source,
checkpoint, data, attribution, and deployment uses receive appropriate clearance.

## Repository policy

Only reviewed metadata, source code, schemas, and explicitly synthetic examples may be
committed. Raw data, preprocessed databases, model weights, contexts, predictions,
evaluator truth, run artifacts, credentials, and caches stay outside Git.
