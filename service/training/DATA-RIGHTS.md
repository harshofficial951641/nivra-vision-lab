# VID source rights and provenance

Audit date: **21 October 2026**. Machine-readable evidence: [vid-source.json](vid-source.json).

## Training decision

The authors' released Harvard Dataverse **V2.0**, version ID **424271**, explicitly declares **CC0-1.0** for the dataset. Its public metadata has no additional use/access terms, restrictions, conditions or special permissions; all 32 RAR files are unrestricted. This supplies explicit dataset copyright permission for controlled experimental training, including a commercially compatible future copyright use. It does not establish complete clearance of every non-copyright right or validate a trained model.

- [Version-pinned official metadata API](https://dataverse.harvard.edu/api/datasets/:persistentId/versions/2.0?persistentId=doi:10.7910/DVN/N4LNZD)
- [Official dataset and DOI](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/N4LNZD&version=2.0)
- [CC0 terms](https://creativecommons.org/publicdomain/zero/1.0/): commercial copyright use is permitted; privacy/publicity rights are not waived by CC0.

The complete deposit contains **45,419,510,634 bytes** across 32 archives. This audit retrieved metadata only. Exact selected archive IDs, checksums and completed download verification belong in the separate download manifest; they are not asserted here.

## Article, consent and remaining uncertainty

The associated [Data in Brief article](https://pmc.ncbi.nlm.nih.gov/articles/PMC11951989/) has **CC BY-NC 4.0** terms for the article. Those terms should not be substituted for the dataset's CC0 deposit. The article's access instructions describe academic, research or instructional purposes, without an exclusive-only qualifier. Preserve this wording as provenance context rather than silently dropping it or inventing an additional restriction absent from the dataset metadata.

The primary full text is retrievable as [Europe PMC JATS XML](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC11951989/fullTextXML), including when the PMC HTML page returns an anti-bot interstitial. Stable XML locators are preferable to line numbers in the minified response:

| Evidence | Primary XML locator | Paraphrased finding |
| --- | --- | --- |
| Article licence | `//article-meta/permissions/license` | Article is CC BY-NC 4.0. |
| Intended access purposes | `//*[@id='para0003']` | Specifications Table describes academic/research/instructional purposes. |
| Participants and counts | `//*[@id='sec0004']/*[@id='para0013']` | Data Description reports 72 volunteers, 3,020 source videos and 3,020 pose-masked derivatives. |
| Anonymisation and pose processing | Section titled `Experimental Design, Materials and Methods` | Face blurring is reported for all videos; YOLOv7 Pose generates the masked variants. |
| Consent and ethics | `//*[@id='sec0007']/*[@id='para0021']` | Authors report voluntary informed participation and University of Asia Pacific ethics approval `UAP/REC/2023/203`. |

Participant consent is **author-reported**. Signed release forms and the exact commercial-use scope of consent were not independently published/audited in this review. Do not describe the deposit as independently verified complete copyright, privacy or publicity clearance.

## Counts, formats and split requirements

- The deposit description says **3,000** source clips; the article says **3,020** source clips and **6,040** files after counting pose derivatives. Confirm actual counts during archive inventory. Six thousand files do not mean six thousand independent recordings.
- The article reports 1,510 violent and 1,510 nonviolent source clips, including 616 classroom, 320 domestic, 434 street and 140 other violent clips. It reports only 10 violent and 10 nonviolent CCTV clips; smartphone footage predominates.
- `_b_` is inferred to mean face-blurred RGB and `_m_` pose-masked video. No explicit filename legend was found. The 16 `_b_` archives total **9,969,293,337 bytes**; the 16 `_m_` archives total **35,450,217,297 bytes**. **Verify contents visually before treating these interpretations as confirmed.** RGB is the intended X3D input; avoid training directly on skeleton overlays as though they were equivalent camera footage.
- Publisher violence/nonviolence/context labels are not independently reviewed contact/intent/injury labels or temporal event annotations. Actor IDs, source-recording groups and near-duplicate relationships remain unverified.
- Keep every source recording, derivative, crop and near duplicate in the same recording group and split. Do not leak paired raw/masked representations across training and evaluation. Identify actor/session grouping where available before calling an evaluation unseen.

## Sources excluded from automatic product training

| Dataset | Reason | Primary evidence |
| --- | --- | --- |
| AIRTLab | Dataset release grants research/educational use; no verified commercially compatible media grant. Its article's CC BY terms are separate. | [Official release agreement](https://github.com/airtlab/A-Dataset-for-Automatic-Violence-Detection-in-Videos#dataset-release-agreement) |
| RWF-2000 | Commercial use and modification/redistribution require SMIIP Lab approval; none obtained. A checkpoint/code licence does not replace dataset media permission. | [Official dataset licence](https://github.com/mchengny/RWF2000-Video-Database-for-Violence-Detection#license) |
| NTU CCTV-Fights | Approved academic noncommercial research only; additional restrictions cover commercial use, redistribution and derived datasets. No account, agreement or permission obtained. | [Official ROSE Lab terms](https://rose1.ntu.edu.sg/dataset/cctvFights/) |

No media was downloaded, accounts created, agreements accepted, authors contacted or GPU jobs run by this rights audit. Downloads performed by another task must be recorded separately.

## Completed local import and provisional pilot

The subsequent local preparation imported **554 videos**, totalling **4,041.179 seconds** and **1,782,008,571 media bytes**, from three pinned archives in [vid-files.json](vid-files.json). Every archive matched the publisher's byte count and MD5; every extracted video has a SHA-256 in the ignored local inventory.

| Archive | Videos | Publisher category |
| --- | ---: | --- |
| `v_c_b_01.rar` | 210 | Classroom violence; observed examples also include campus exteriors |
| `nv_b_01.rar` | 204 | Nonviolent |
| `nv_b_06.rar` | 140 | Nonviolent |

Decoded durations range from **2.567 to 38.182 seconds**, exceeding the article's stated range. The trainer uses measured durations and full four-second windows rather than assuming the article's range. The 48 screened `_b_` examples contain RGB scenes with face blurring, without pose-only rendering. This confirms the sampled format, not every archive or every participant's anonymisation.

The pilot screened **48 clips using 16 timestamped frames each**: 8 provisional positives and 28 provisional normals were retained. Twelve were excluded or ambiguous; two retained normal clips have only early, explicit normal intervals. At that pilot stage, the remaining 506 videos had not been visually reviewed. Decisions and limitations are recorded in [positive-review.json](positive-review.json), [negative-review.json](negative-review.json) and [campus-negative-review.json](campus-negative-review.json).

The [pilot manifest](vid-pilot-v1.json) contains 36 recordings and 76 eligible windows (14 positive, 62 normal). All VID footage remains in **one unresolved training cohort**. There is no VID calibration or holdout split. Sampled-frame screening is provisional assistant review, not continuous-motion review, human annotation or independent ground truth. It cannot support an accuracy or improvement claim.

## Round 2 expansion

Two further archives from the same pinned V2 release, `nv_b_02.rar` and
`nv_b_03.rar`, added 378 recordings (112 and 266). Their combined download size
was 1,390,546,297 bytes. The parent independently checked the saved official
release metadata, CC0 declaration, unrestricted file status, exact IDs, byte
counts and both archive MD5s. [vid-extra-files.json](vid-extra-files.json) records
the pins. Separate extra inventories preserve the original inventory.

The imported pool now totals **932 videos**. Across the pilot and round-2
reviews, **258 recordings** were visually screened: 96 retained, 162 ambiguous
or excluded, and 674 still unreviewed. The current
[manifest](vid-round2-v1.json) has 39 positive and 57 normal recordings,
producing 65 positive and 91 normal four-second windows. It was rebuilt from
the three inventories and eight review files with an identical SHA-256.

The new reviews preserve their individual sampled-frame limitations. Seventeen
normal spans additionally have every-frame contact-sheet coverage, whose
presentation-time extent was independently verified. This is still assistant
screening, not human ground truth. Every VID record remains in the same
training-only cohort. No independent evaluation split or wider participant
release scope has been inferred. See [ROUND2-RESULTS.md](ROUND2-RESULTS.md).
