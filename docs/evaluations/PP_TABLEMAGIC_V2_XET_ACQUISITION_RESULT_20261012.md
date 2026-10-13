# PP-TableMagic v2: second asset-acquisition result

**Decision: verified assets, parser quality untested.** The separately frozen [Xet acquisition arm](PP_TABLEMAGIC_V2_XET_ACQUISITION_PROTOCOL_20261012.md) completed on the original 12-PDF VRDU ad-buy source lock. It verified all **54/54 active files** for the nine-model full-table profile: **16** exact files rehashed and copied from the sealed first arm, and **38** files downloaded once each from pinned official repositories. The parser was **not** run in this arm. The first raw-HTTP arm's no-score outcome remains unchanged.

## Frozen inputs and verified outputs

| Item | Observed result |
| --- | --- |
| Selection SHA256 | `b843d48146a60f02bb206900ee06d446eb82ba484a3781c291235864b5230d2d` |
| Cohort SHA256 | `98f4fcbd6521594304da3a80104362cf89174c87c27ed08ce90a1158fef4bc90` |
| Gold SHA256 | `8a631bffbf439ccc8376f84cbf7d4af25c86d35c0ccc7996ce3b23e6085138bf` |
| Manifest canonical SHA256 | `85199082278e21b5d46a3c3d6db5f1d417b7a222964d4a48838d44c9bd53d335` |
| Downloader LF SHA256 | `b66c9b6c40185d1b4374807421843facf7852854588eaeaead84819fa2bb42db` |
| Final model inventory | 9 active models; 54 verified files; 1,344,345,025 expected asset bytes |
| Acquired through pinned Hub/Xet | 38 verified files; 1,207,234,166 asset bytes; 7 new weight transfers entered `xet_get` |
| Reused from sealed first arm | 16 rehashed files; 137,110,859 asset bytes |
| Failed or skipped asset receipts | 0 |
| Elapsed time | 447.25 seconds |

The frozen runner's exact `verify_models` check passed. The acquisition ran under the pinned Paddle Python 3.11 environment with `huggingface_hub==2.2.0` and `hf_xet==1.7.0`. Public assets used `token=False`, an isolated Hub/Xet cache, and the frozen resource watchdog. Small repository metadata files were permitted to use normal Hub HTTP; the seven newly acquired SHA256-locked weights entered Xet, and weight HTTP fallback was blocked. These observations establish verified local files, not extraction accuracy or source-cell provenance.

The raw acquisition root is `C:\DocAI-TableMagic-Xet2` (outside Git). Its 187-file inventory seal has root digest `08d259bcd3d78a4324c45870c4c82a3aae899430944e69736999f80ac70c6d0e`; the seal file SHA256 independently rechecked as `a0f7eeaf53711ec131d21ad76403a88c7b91670543a846e8b35b38ad4c822f62`. The receipt file SHA256 is `270293d359a7ab0238708200c5028271a9eb2c77cb629e7380e7b59ae14f02d2`. The raw summary SHA256 is `c13fced4708836fa4083862058ae432f3e6a4cc666c6ce3559d96afa928a1c5e`. No raw model, cache, log, receipt, or PDF was committed.

## Bound checks and launch event

The maximum sampled child process-tree RSS was **204,197,888 bytes** against a 3 GiB cap. Minimum sampled available host RAM was **8,066,183,168 bytes** against a 3 GiB ongoing floor. Minimum sampled free C: space was **6,562,062,336 bytes** against 4 GiB; minimum free E: space was **3,850,731,520 bytes** against 2 GiB. The final root used **2,551,728,009 bytes** against a 3.5 GB root cap. None of the 38 asset calls or resource guards failed.

One shell launch immediately failed before creating the new root: calling the script by file path omitted the repository parent from Python imports (`ModuleNotFoundError: No module named 'product_eval'`, exit 1). After confirming the root was absent and no transfer had started, the same committed code was invoked as a module with a shell-scoped `PYTHONPATH`; no asset retry or protocol change was made. The observed launch error was preserved separately at `E:\DocAI-Benchmarks\tablemagic-xet2-launch-failure.json` (SHA256 `1eaf8943e292daa8a510770429470bfac37cb62e1531a5f583c9e70ab02f7a326`). This sidecar is a post-run record of the console error, not an automatically generated downloader receipt.

**Next gate:** the already frozen 12-PDF full parser pilot must run and score table HTML rows against all 219 linked gold rows, retain failures, and audit cell-to-source alignment. Asset acquisition alone does not justify parser or product promotion.
