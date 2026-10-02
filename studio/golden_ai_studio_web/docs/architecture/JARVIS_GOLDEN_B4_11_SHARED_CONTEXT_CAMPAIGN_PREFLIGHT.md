# Jarvis / Golden B4.11 Shared Temporal Campaign Preflight

**Result:** `PASS_WITH_RESTRICTIONS`  
**Validated baseline HEAD:** `4196f24be4159864d2a7dd69824c0b50ed634366`  
**Branch:** `main`  
**Execution:** planning-only; no new samples or external trading/tester activity.

## Campaign integrity

| Identity | Value |
|---|---|
| B4.9 campaign | `campaign_b49_xauusd_m1_temporal_01` |
| B4.9 manifest fingerprint | `0f09221134098dc0979867ec1fe1ab4429f864c9f870d2e195b6cd848b61aab4` |
| B4.10 campaign | `campaign_bf3389bc66f0ac7777a3a06719ac5851` |
| B4.10 manifest fingerprint | `0df8521de44446de48141eb59b8ca884baca7fe483407239c4a952c2a25d7f0f` |
| Campaign status | `PROPOSED_NOT_AUTHORIZED` |
| Manifest changed / successor | `NO` / `NO` |
| Robots / planned runs / new executed runs | `2` / `16` / `0` |
| Context-plan contract / fingerprint | `jarvis-b4.11-context-plan-v1` / `62090078ae10a7a124bb8e9aec420015e523468a2b777c00b942ccca995beab6` (clock fixed at 2026-10-02 for report) |

The two identities remain isolated:

| Robot | Source SHA-256 | Compiled SHA-256 | Parameter fingerprint | Scope |
|---|---|---|---|---|
| `EA_Canal_Pullback_MT5` | `0f1ba3526de5e7b679281e38136479beb99dd707fd1b02db1d960ffae103aff4` | `e239e0dfc1c6a10c4bd4f8758b1913946b2423cd0901b8f3486b910fe56267cc` | `7953a3fa4ca05b223411fca3` | XAUUSD M1; B4.9 verified preset |
| `Robo_Tendencia_MA9_21_50_Volume` | `e7bcba2bb39dc6ab7a7389e32fa50f665e2caf62b1f2ecec6c4d6d5362d1130f` | `22f243a500aaf567f291cbaecf11ca87db89986e1be28c1e405009e9034629f4` | `9da7c5af45bacfb4f62de780` | XAUUSD M15; complete source defaults; compiled identity must be revalidated at future preflight |

No Range artifact was selected and EMA was not promoted. B4.10's `OnTester` semantics are preserved as unknown / robot-specific; Canal's documented custom robustness score is not interpreted as profit.

## Shared window model

Canonical identity is SHA-256 over the versioned semantic tuple: symbol, timeframe, start, end, explicit timezone (`UTC`), and B4.7 warm-up policy (`7` calendar days). Tester model and robot identity are excluded from market truth. The B4.10 calendar has 8 date windows but two timeframes; therefore it contains **16 unique technical market windows**, each referenced by one run in this proposal. There are 8 independent calendar macro-window identities, each referenced by the two robot runs for that date. Thus the sharing contract is tested without falsely merging M1 and M15 technical contexts.

| Window | TF | Dates | Fingerprint | Run | Robot |
|---|---|---|---|---|---|
| `market_window_2bb9da8f5a5380a3edc6b01b` | M1 | 2026-11-02..06 | `2bb9da8f5a5380a3edc6b01b7baaf71e804463ae3c884a5bbeb025464f6bc043` | `run_d2a9061f911389bd140492c996d5b0ff` | Canal |
| `market_window_1fcf576c00897efeddfd22e2` | M1 | 2026-11-09..13 | `1fcf576c00897efeddfd22e2fd0fa6b4783c7bc4790b695f0019647564ca237b` | `run_9dbcd7e59f0eacd79b6e39c231f34a44` | Canal |
| `market_window_3f94ad6f21c90d05046dc355` | M1 | 2026-11-16..20 | `3f94ad6f21c90d05046dc355cceff16559c9c3827d32934c5e06934e8834c83c` | `run_dc6cdb51979b01c7b0537db705d771c8` | Canal |
| `market_window_29e2305edefa4f73940fb0de` | M1 | 2026-11-30..2026-12-04 | `29e2305edefa4f73940fb0de8f28a081c6dc192eab3fffc19b5d297396dee7c9` | `run_3c25836966ad1fed1309c5e4f356b2b3` | Canal |
| `market_window_9b27fe03551836602425527e` | M1 | 2026-12-07..11 | `9b27fe03551836602425527e9c14acec097eaea422c6e7d5405d93bcd616e45f` | `run_e48ac1243f1ca4d02cf4a5a01393c62d` | Canal |
| `market_window_94b64f35330a4a00176edce2` | M1 | 2026-12-14..18 | `94b64f35330a4a00176edce2c5b023858c07c98e1581f69dde4ea2a66447a3b2` | `run_e4ec91b9aad8a12d7cfee367c30312a4` | Canal |
| `market_window_e94f9d51f063d551a8f031be` | M1 | 2027-01-04..08 | `e94f9d51f063d551a8f031be59b315c4b279ad2941a7b3829b9668ea24ef8f0e` | `run_99832948aa35b284dfeab7c44da88b9e` | Canal |
| `market_window_f6e01a559dead6806f74524e` | M1 | 2027-01-11..15 | `f6e01a559dead6806f74524e61deb0256838d25a4d957e7f7c2cd3c1e949633a` | `run_15b17e5d3ad96d6cefdbade8872fb44f` | Canal |
| `market_window_1d75b1e211e5ca52d53d4f4a` | M15 | 2026-11-02..06 | `1d75b1e211e5ca52d53d4f4a4ad2c10e3c3789f1c4867af02f74290f8876cc5f` | `run_e3cd3139c6f75ffe6cf96a0aa799e12a` | Tendencia |
| `market_window_33263e8893ee5f0af3be49dd` | M15 | 2026-11-09..13 | `33263e8893ee5f0af3be49dddc32244a863f3d3da94a7df1d1336447e2ac86df` | `run_ac5aad9da8491e6975b31116e35488f7` | Tendencia |
| `market_window_ada7e0d0bdca696762a880c7` | M15 | 2026-11-16..20 | `ada7e0d0bdca696762a880c7b7f11b07e034768aee88e45500d1949bf5c12bd9` | `run_cc84a3bbc3f082475db4599029415cc0` | Tendencia |
| `market_window_e50770f583f7b65aece28dec` | M15 | 2026-11-30..2026-12-04 | `e50770f583f7b65aece28dec86cd4e4c64a1f0f6de949a70dc1a9c4da26b87a2` | `run_c53cc74f58accb800a4a986861fcd8cf` | Tendencia |
| `market_window_e3b88d9e3b5e8487aad5a6a6` | M15 | 2026-12-07..11 | `e3b88d9e3b5e8487aad5a6a6a48ca8f72465b627fc5d05bb84275e410bcb5ec2` | `run_f77f0d2d503834f6906a9a17d9bb1ee0` | Tendencia |
| `market_window_750e2b4c0b022152b8a30850` | M15 | 2026-12-14..18 | `750e2b4c0b022152b8a30850860b0a1c3660ad6283ea6ae5bd4cb241dc466634` | `run_1d055df1c1fad083e1164d9ffc564569` | Tendencia |
| `market_window_d00aaf8c669cd9ef09ceb929` | M15 | 2027-01-04..08 | `d00aaf8c669cd9ef09ceb92972f31734e4526b8e6b85fc0a8ac62c2d73cf810c` | `run_bc37db106940a24f6be069c00fd922e7` | Tendencia |
| `market_window_e72018807bf0e2532ea37d3b` | M15 | 2027-01-11..15 | `e72018807bf0e2532ea37d3b85ee96cfbf525d083cba76c60c29262f8428594f` | `run_29e903ccf88c2f0aedf084489ce63c0a` | Tendencia |

Shared macro-window identities (same macro identity is referenced by both runs shown):

| Macro window | Dates | Macro fingerprint | EX-ANTE fingerprint | POST-WINDOW fingerprint | Runs |
|---|---|---|---|---|---|
| `macro_window_065b55b6558771faa535b4b0` | 2026-11-02..06 | `065b55b6558771faa535b4b03b2bf3a8c79d5ba0d7f066558c0df35b0300204d` | `ae5660976e5ec0a1b5faf2a733d4bdff32209dc4cfb5140b2dbc310f2e732712` | `37973f034f877b8984670e067916799f297f01fd79c546595df79e77dc5257b2` | Canal `run_d2a9061f911389bd140492c996d5b0ff`; Tendencia `run_e3cd3139c6f75ffe6cf96a0aa799e12a` |
| `macro_window_0afdfb01518d70fa7e28090a` | 2026-11-09..13 | `0afdfb01518d70fa7e28090a3d18a163249145b7e7458a498c3f60352d61490a` | `b34f2dea569fae38f0a6c7d68514c096ad39aba79d5577987646e8f35f8a1ad3` | `3568be669f692ee8b5e375ae6ef7f6eb9e59704bc17e5fa87cbca254751fd544` | `run_9dbcd7e59f0eacd79b6e39c231f34a44`; `run_ac5aad9da8491e6975b31116e35488f7` |
| `macro_window_e0f83af2950998266178bfc5` | 2026-11-16..20 | `e0f83af2950998266178bfc58eae329d72b4f46b023ae417337d691eb63ae247` | `a01246a38ef943679a0ca298ed26e4bdf36dd98445d230b6bc69b18382aa6640` | `4c3df78ef646750bfd04be429fd9c817ead895a4f5dc025ba47495fd09112f98` | `run_dc6cdb51979b01c7b0537db705d771c8`; `run_cc84a3bbc3f082475db4599029415cc0` |
| `macro_window_442c4d39be1e19c670d8bb1e` | 2026-11-30..2026-12-04 | `442c4d39be1e19c670d8bb1e721beadf45cc3e905f2ecd00772d3234eef77c47` | `4dee1591ad1ad8601b55e0183cc01e3eb599070757cba48850d1660f11891c63` | `9af605b14de8710c51bdc3a3eeb3e6887c8ceb7c1af6e0657238be08e68e2a84` | `run_3c25836966ad1fed1309c5e4f356b2b3`; `run_c53cc74f58accb800a4a986861fcd8cf` |
| `macro_window_e79b19d65e70565706d4708a` | 2026-12-07..11 | `e79b19d65e70565706d4708a25624267e75d70c43b788428be775748a8acc269` | `5f1fae69050a5b8966a68a52dedeac78c2329c043fa9a8834a4ba74a6bf05467` | `5f9ad6bf1ddc2169cbba7e3551ae5cf41f8f9efd7df44af9cd89e0a9b3ce7a49` | `run_e48ac1243f1ca4d02cf4a5a01393c62d`; `run_f77f0d2d503834f6906a9a17d9bb1ee0` |
| `macro_window_a644e1e89c91fb3432949093` | 2026-12-14..18 | `a644e1e89c91fb34329490935717ce81c434bbb74a1778ac6c345a62fd6af322` | `0279d77d8631890a6ca5239f0fdf18205c1cadc09f02bab99e733cf949eb1891` | `ec2f5e9edc1dd91d1698e453d82ed77485784a380e7fc97acedd907d5237b75e` | `run_e4ec91b9aad8a12d7cfee367c30312a4`; `run_1d055df1c1fad083e1164d9ffc564569` |
| `macro_window_e59c4b0e37e6aee08cc42b97` | 2027-01-04..08 | `e59c4b0e37e6aee08cc42b97b373c1bfd521da7f45ba1bf01afbe73b97ebb7ba` | `dd855df096f5c37ebaa90bb96aa4265247070f80372c0b92ca00d4c4fc873cf3` | `cfa9b68a32bfffb5b2a876a8842d0d647a8034f3076adb12898614d266019389` | `run_99832948aa35b284dfeab7c44da88b9e`; `run_bc37db106940a24f6be069c00fd922e7` |
| `macro_window_e7ec3cdeb75219c4579fafc4` | 2027-01-11..15 | `e7ec3cdeb75219c4579fafc4723327d27303e2970161e1cebae3597c7218649a` | `b7b24ac430a924dd3ca208917533bb77b3c7523e3be8de4feef60b0c35d4e280` | `8382a2e40e32626aa2c4d3612a7d063c28329051a717f2d97f4c37762ba9f332` | `run_15b17e5d3ad96d6cefdbade8872fb44f`; `run_29e903ccf88c2f0aedf084489ce63c0a` |

No context payload is fabricated or duplicated (`0` created). Pre-window technical contexts await point-in-time acquisition/freeze. Future post-window market contexts and outcomes are absent.

## Macro and temporal readiness

The read-only planner reuses B4.8's `jarvis-b4.8-macro-event-v1` semantics, release/availability ordering and cutoff model. Each calendar window has shared EX-ANTE and POST-WINDOW identity/fingerprint pairs, shared by both timeframes, not tied to robot or test-run identity. Schedule snapshots/version, immutable source bytes and ingestion-time proof remain pending; B4.8's existing curated source is offline and notes that raw primary-source bytes are missing. No events were fetched or guessed.

At report clock `2026-10-02 UTC`, all 16 windows are `NOT_EXECUTABLE_FUTURE_WINDOW`; complete `0`, in progress `0`, future `16`. First window is `2026-11-02..06`. Aware injected-clock tests cover before, during, and after a window. Completion alone still never grants authorization.

## Configuration and sample fingerprints

The following rows give `run: scientific-config fingerprint / output-route-plan fingerprint / sample fingerprint`. Scientific fingerprints are unchanged from the immutable B4.10 proposal; route plans are not materialized files.

| Run | Scientific config | Output route plan | Sample |
|---|---|---|---|
| `run_d2a9061f911389bd140492c996d5b0ff` | `7af529cbffa33bbbc2038b7658154090a1178fe5b93b3c8913628f592029f8c9` | `be4187d0f66c9ad3aa3c9a05dbecadde2729159109d5fa68469cec7727cc6925` | `cb9478c037a6bb686c071d334576717acd814e51b76fac3f1e73dffe2ece87e3` |
| `run_9dbcd7e59f0eacd79b6e39c231f34a44` | `288d65e0b1557f8ff5fb5053a816fc7c98072f09da6e8f31b8e30dcbf0f9ec8f` | `cb57897c0b8f03ad30159acbce5b0f3a137dcc1c639ce05d329cc8959a0dee26` | `63efc3495acda835ccd9bc34218867e16e2080b940e3e806913a8b31caba6200` |
| `run_dc6cdb51979b01c7b0537db705d771c8` | `4b1e1a07b32ed4879b4f14f855b961540b61342eccd757cc1ddb8aa3edb8414f` | `663e10d87645f192efe22436306bb0471456a9c17c577d5dd34bf24cf262cd4f` | `a35c6b7df930306a406266503e1ba29b1809cdd105c3098307667552db869295` |
| `run_3c25836966ad1fed1309c5e4f356b2b3` | `9b32cb3f65f89bb3f4413ea8399c5f814c94f15696fb192f8e6875987804a3fe` | `a45caeaeb4425288e9f0893106eea97b8fe46b51794703b2a7e8062e618408e9` | `688aa9b1ea67802b87a91a5caa291d964ce0e901162d4f48c427baef219fe3d5` |
| `run_e48ac1243f1ca4d02cf4a5a01393c62d` | `7776442ab74f50387c210e7277af87afa62a3ff5084fdfbc9629deed08aff59d` | `cac2638f47b77de1f76efe85fa7549ae2b30c62ee4a2cf347973f45a3b0f1375` | `341ab3134633fd73eac933e136f4f649284635e5b6743e0859878cc3a1ff54b3` |
| `run_e4ec91b9aad8a12d7cfee367c30312a4` | `affbe259d63cd565eba944e706f22b82d77fb37e06ba34860a0c7c76178746b6` | `1ac1002bc698ee94020ba9bb8fb76b934ff7e8e54bc285744c0b638dc8948979` | `d97e474f38acc4297632934de55723384593696aba0493c15005fa69bf3664ba` |
| `run_99832948aa35b284dfeab7c44da88b9e` | `e2e4379d7ed2c7d5ca9f6440f02e4f3361dad2cc0f21a17134c82030bd40b3fe` | `3ef3436fab578fcd7f1614e477c912461f57df609dae7aeb203c80571ef920f9` | `aadfe6dc1b22ffb7cbab48c46913ded012ee4bdba8d3a63a6416be584a06c0b1` |
| `run_15b17e5d3ad96d6cefdbade8872fb44f` | `940e84b8c79ddab3bccf81ee11129ad3388e831649168422a2bbfd7c07b416bf` | `ce4a3d58632ac5276993f44e89f5be7264ead0714b327e3d98816c4697728297` | `9f93c4b1537efc5743b4544930b9d7324375100275c9627167a1985c5e9fcdde` |
| `run_e3cd3139c6f75ffe6cf96a0aa799e12a` | `c4bac598ff53d7a17f692cead8ee3346a28a7c4ff5b64f9cf0a9059840f9e6ff` | `d080a56c98c1c232041c9441a397fe15ecf4a0ecf029f302ebbd9b033cc1e039` | `6716eaa11b29d8bfbc9150d487ee0e2b116ccdd9401442fb6d73a587d4d75fe6` |
| `run_ac5aad9da8491e6975b31116e35488f7` | `50a27545c3325fc8e8c15d07184538c01c49903d0830ae938aa77160ae29d092` | `04b04ac87e1c9380820de9bf73806fd208a2e1a8460d631439bf57ff04df871a` | `0fd3820a98fa9dd11152b84c2e19fe80ede0b26c1df00833c26b673f684e9312` |
| `run_cc84a3bbc3f082475db4599029415cc0` | `a5e53c2c79911e1075f48f5e1e004e896e783b98da2c64f282d6778d50920f46` | `066a3bb2c578a98ec727de78d5b3f4f1387d75362eb35e35eaf71ebd092549fd` | `2778b373e1a66b2b4ca92b222801cc4506e29be67fe677a03c3dc23c8f1db0a7` |
| `run_c53cc74f58accb800a4a986861fcd8cf` | `32ea55be172712a6f46f910bae32952355b0e17b276db1c2056851db197903d7` | `30567c5eb58cc182ae7566668d057971c7474dc241503ca3390ede1c1bc2a61a` | `8c9aea7451df0a395102b298cafe43c9c445547a12d9c8be35c71d3ed088c1d4` |
| `run_f77f0d2d503834f6906a9a17d9bb1ee0` | `49643d43321d57048c1d10ae278be7ed1dd89020ae9a323fcd6e2b121a3ee662` | `14967ec3d8f2c97aa8d90dbd4d82ac840e980b804fff2dda4b1c79ee291a004d` | `4c96362d317e671eed0a709cf365045bcff36c9b7cde2b833c1d54ca89a40957` |
| `run_1d055df1c1fad083e1164d9ffc564569` | `355cd23fdda77837cb5a11556dfc29ecda8e74e2803a80faa56d6163e5ed4e66` | `afda2e37c696a00d1af1a7de27cda21499b0a2225535c4fb1d4a3e0339dd6cbe` | `9416d93fb52e891de88d28ab0c15ec86c8ec1003ef2a1c85291a896cd943c0bb` |
| `run_bc37db106940a24f6be069c00fd922e7` | `f8adcc01d95aa4d25e8c134489e880b84cbbf3ac574dae6ebaf843fd55da689c` | `58b5597f19a2aec72c4f50a9d70d3e6c56293205429b88e81ea82a67d6649af0` | `dadfcf733fa2ef77af5840174935092272b306783ef6d5645c6b3622774f1e74` |
| `run_29e903ccf88c2f0aedf084489ce63c0a` | `cf617ad66041dfbac76ec736d977bf0107e27c74a98f57bf3143b445dd037849` | `f49904e3f764aec8a5fc1a56b3a014b61f60d364eb620653c7f861392ccae333` | `aa9c80e95a6e4ce22bd9c02af57ab0f7afb5b9429a6427651e3739bfa5887c30` |

## Catalog, memory, UI

Catalog and schema unchanged; no database opened for mutation, migration or writes. No new memory engine. This is an ephemeral read-only projection owned by `JarvisService`'s existing Robot Intelligence read model and has no execution route. Control Center shows campaign/manifest and plan fingerprints, all technical windows, timeframe, date, fingerprint, run count/lifecycle, macro sharing count, scientific-config readiness, pending materialization, not-authorized/not-executable/backtest-only/not-live labels. It has no execution controls. Visual validation was static (`node --check`); no browser or desktop was launched.

## Tests and checks

- Focused B4.11 + B4.10 + B4.9 + B4.8 + B4.7/B4.7C/B4.7D + B4.6 + B4.3 + Catalog + Tester + Memory + Security + Audit: `224 passed, 4 warnings`; final B4.11-only rerun after the shared sample-identity case: `10 passed`.
- Full repository pytest: `2177 passed, 23 skipped, 45 failed, 4 errors, 92 subtests passed`. Failures/errors are outside the B4.11 files: legacy service/Voice/runtime/research tests, Windows SAPI requiring missing `pywin32`, and ad-hoc/live test modules collected as pytest tests without their intended arguments. No B4.11-focused failure. Broad pytest did include mocked provider-contract cases and attempted local Windows SAPI initialization, which stopped at missing `pywin32`; no successful voice initialization was observed. Since the suite was not instrumented for network-call auditing, zero provider calls cannot be asserted from this run.
- `py_compile`: passed for the new planner, updated read model, and B4.11 tests.
- `node --check src/app.js`: passed.
- `git diff --check`: passed; staged diff is empty before checkpoint staging.
- Scoped scan for private-key headers and AWS access-key identifiers: no matches. `gitleaks` is unavailable in this environment.

## Safety and remaining restrictions

MT5/MetaEditor/Strategy Tester/MQL5 compile/trading/orders/broker mutation: not run. Database/schema/catalog/device registry: unchanged by B4.11. Voice hardware: not initialized; one unrelated full-suite SAPI test stopped during dependency import (`pywin32` missing). Provider runtime-call count: not independently instrumented by the broad suite. Pytest produced an extra untracked backtest JSON under `config/backtest_results/`; it is preserved and excluded from B4.11 staging. These test-suite observations do not change campaign state or authorize external operations.

Remaining blockers before any future tester preflight: the windows must complete; point-in-time technical data and schedule snapshots must be acquired and frozen with provenance; macro availability/ingestion proof and immutable source artifacts must be validated; compiled Tendencia bytes must be revalidated; production INI/output artifacts must be materialized and reconciled; catalog association review and a fresh single-use human authorization must be obtained. Holdout outcomes remain inaccessible until a separate review.

**Recommended next gate:** B4.11 review of the read-only preflight and planned materialization contract. Recompute fresh identities only after a window is eligible; do not request tester authorization now. Earliest currently planned window begins `2026-11-02`; tester preflight is only possible after that window ends (`2026-11-07 UTC`), subject to all restrictions above.
