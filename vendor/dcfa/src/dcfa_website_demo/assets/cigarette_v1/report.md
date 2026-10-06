# Agentic TabCF report

![Estimated outcome distributions and summaries](interventional_summary.png)

### Distributional analysis — Track T · Real data · Exploratory estimates

Prices: 100 to 120 CPI-deflated cents per pack. All differences are 120 minus 100.

State-year sales per capita; each observation has equal weight.

**Sales quantiles**

Levels and changes are in packs per person per year. Each row describes a percentile of the estimated sales distribution; the median is the 50th percentile.

| Quantile | Price 100 | Price 120 | Change (120 − 100) |
|:---|---:|---:|---:|
| 25% | 107.2 | 86.3 | -20.8 |
| 50% | 117.8 | 95.8 | -22.0 |
| 75% | 129.4 | 105.8 | -23.6 |

<details>
<summary>Technical appendix and evidence index</summary>

- Run ID: `run_a59f587b55768ef3b8632887`
- Result bundle: `bundle_d4f43ef6861dd54996886842`
- Specification: `spec_2ab6509e9454758b836df9cf`
- Dataset hash: `sha256:fae33858f487366d0acaaab719b693615cbcca3ecf7de75e67e209c441e9029d`
- Evidence status: `development_only`

Diagnostic values and support assessments are retained in result_bundle.json.

| Reference | Query | Validated value | Evidence ID |
|---|---|---|---|
| [1] | `quantile:0.25:0` | 107.155 packs per person per year | `evidence_244cb3ebaa1b9a1bcb782211` |
| [2] | `quantile:0.25:1` | 86.3084 packs per person per year | `evidence_d293e489175b8df36f67eb8d` |
| [3] | `quantile_difference:0.25` | -20.8468 packs per person per year | `evidence_f101c44454f202b1010848f7` |
| [4] | `quantile:0.5:0` | 117.761 packs per person per year | `evidence_11cf2fd495ebdc1b10ab06e3` |
| [5] | `quantile:0.5:1` | 95.8096 packs per person per year | `evidence_4ab574aaf5611b5c9850d73a` |
| [6] | `quantile_difference:0.5` | -21.951 packs per person per year | `evidence_1cc9c859c12c2c8817cc1f75` |
| [7] | `quantile:0.75:0` | 129.399 packs per person per year | `evidence_9ccb7ee9fb9d310485217417` |
| [8] | `quantile:0.75:1` | 105.772 packs per person per year | `evidence_044b399630d14ae582c1481e` |
| [9] | `quantile_difference:0.75` | -23.6268 packs per person per year | `evidence_761f33e2d823881008f4f8f9` |
| [10] | `cdf:0:0` | 1.78039e-06 probability | `evidence_e2b59ebb7b55a323de7b4d1d` |
| [11] | `cdf:0:1` | 1.88645e-06 probability | `evidence_b7a67186954999fc9449d7c7` |
| [12] | `cdf:0:2` | 1.99848e-06 probability | `evidence_228898f82e9e731e392ddba2` |
| [13] | `cdf:0:3` | 2.11957e-06 probability | `evidence_6c86dd7843a1a78b76594d3d` |
| [14] | `cdf:0:4` | 2.24882e-06 probability | `evidence_4e130d65e19c4b747446a83e` |
| [15] | `cdf:0:5` | 2.38934e-06 probability | `evidence_aae3f2172761a022b09a17d7` |
| [16] | `cdf:0:6` | 2.53907e-06 probability | `evidence_af59478914a7ad388f28e813` |
| [17] | `cdf:0:7` | 2.70745e-06 probability | `evidence_94e8bf056fcade7351afe26e` |
| [18] | `cdf:0:8` | 2.8922e-06 probability | `evidence_eb22f19d5c20987dafe6c532` |
| [19] | `cdf:0:9` | 3.0957e-06 probability | `evidence_d607a62694ae06e0238ce5e7` |
| [20] | `cdf:0:10` | 3.33042e-06 probability | `evidence_1f0c873b09f6f8afaa2d5fe2` |
| [21] | `cdf:0:11` | 3.58488e-06 probability | `evidence_6826385b04caa472bd0af000` |
| [22] | `cdf:0:12` | 3.86595e-06 probability | `evidence_ff13770dc3a557c84b50c45d` |
| [23] | `cdf:0:13` | 4.19439e-06 probability | `evidence_8c2bdeaa71013086306d4303` |
| [24] | `cdf:0:14` | 4.57344e-06 probability | `evidence_a458fcc99dcbf3c311ae247e` |
| [25] | `cdf:0:15` | 5.02201e-06 probability | `evidence_c2d94e2759b5e651d91afa54` |
| [26] | `cdf:0:16` | 5.51278e-06 probability | `evidence_6de0635312538caf152295e6` |
| [27] | `cdf:0:17` | 6.08599e-06 probability | `evidence_df6d1b2152c8483404658360` |
| [28] | `cdf:0:18` | 6.76067e-06 probability | `evidence_528f7f34318611337bdf6245` |
| [29] | `cdf:0:19` | 7.53053e-06 probability | `evidence_7c2215b4f0378e5a9fce7871` |
| [30] | `cdf:0:20` | 8.41553e-06 probability | `evidence_24ea6dddff1c754e4d014dc1` |
| [31] | `cdf:0:21` | 9.45741e-06 probability | `evidence_c86802fe09149de7882484f1` |
| [32] | `cdf:0:22` | 1.06732e-05 probability | `evidence_227e57021d2a38d8c0741dcc` |
| [33] | `cdf:0:23` | 1.21001e-05 probability | `evidence_0fc25db5ba4c32f6a76e826e` |
| [34] | `cdf:0:24` | 1.37522e-05 probability | `evidence_49372f8f57b4c260608ed9cc` |
| [35] | `cdf:0:25` | 1.56831e-05 probability | `evidence_6f92e7223c4d6dde7a7c1857` |
| [36] | `cdf:0:26` | 1.79556e-05 probability | `evidence_5d3bc95d1cf37ea234f8c8af` |
| [37] | `cdf:0:27` | 2.05461e-05 probability | `evidence_c1d8bf866dbff30b00c90f8c` |
| [38] | `cdf:0:28` | 2.35056e-05 probability | `evidence_4ac14c7ed56bf44b9eb0a014` |
| [39] | `cdf:0:29` | 2.69492e-05 probability | `evidence_e79907125db698841c6c8862` |
| [40] | `cdf:0:30` | 3.0858e-05 probability | `evidence_e16f0caff46f923c5f5e546b` |
| [41] | `cdf:0:31` | 3.53011e-05 probability | `evidence_9189db379cf98887dc7b69a7` |
| [42] | `cdf:0:32` | 4.06092e-05 probability | `evidence_25157adef6f848595c899375` |
| [43] | `cdf:0:33` | 4.66023e-05 probability | `evidence_00bbd8106f8c1a181d7e1f44` |
| [44] | `cdf:0:34` | 5.38172e-05 probability | `evidence_8929c73bcfe6803fb6640ca3` |
| [45] | `cdf:0:35` | 6.21502e-05 probability | `evidence_fd4c423f75b5daa9c3d38097` |
| [46] | `cdf:0:36` | 7.2039e-05 probability | `evidence_8de81274e9bd83d2f59d8967` |
| [47] | `cdf:0:37` | 8.37513e-05 probability | `evidence_b323d863201547e1c8cb3cf4` |
| [48] | `cdf:0:38` | 9.75376e-05 probability | `evidence_c86576635fd6ca8d4722c610` |
| [49] | `cdf:0:39` | 0.00011339 probability | `evidence_3f89eeb5d65ac135d9da693a` |
| [50] | `cdf:0:40` | 0.000131498 probability | `evidence_4fca56d0f3b746f7593b1874` |
| [51] | `cdf:0:41` | 0.000152529 probability | `evidence_17ed01c94b9bdbcf3a790e6f` |
| [52] | `cdf:0:42` | 0.000176142 probability | `evidence_86ba6539db322da77da4e7f0` |
| [53] | `cdf:0:43` | 0.000204369 probability | `evidence_e95e0a4a5561ab8e04114014` |
| [54] | `cdf:0:44` | 0.000237471 probability | `evidence_6552e5f1af6fd667eeff75b0` |
| [55] | `cdf:0:45` | 0.000274517 probability | `evidence_6ebaa9f8b58a9d5d99b04fec` |
| [56] | `cdf:0:46` | 0.000317997 probability | `evidence_29c1512ba9d62c571ee44f2a` |
| [57] | `cdf:0:47` | 0.000368771 probability | `evidence_9b36f1f57d8f199cb78c81a3` |
| [58] | `cdf:0:48` | 0.00042864 probability | `evidence_cc12e00dbee0ac52a21b973c` |
| [59] | `cdf:0:49` | 0.000499948 probability | `evidence_649daa3bc04fa4a2df9c2fb3` |
| [60] | `cdf:0:50` | 0.000583448 probability | `evidence_634fb07cd925619c31bd6d27` |
| [61] | `cdf:0:51` | 0.00068312 probability | `evidence_cde0b0472f4528240c640a93` |
| [62] | `cdf:0:52` | 0.000795255 probability | `evidence_33f06cef812d1149e8308843` |
| [63] | `cdf:0:53` | 0.000925525 probability | `evidence_52a7eb7246b94f61b10c7925` |
| [64] | `cdf:0:54` | 0.00107307 probability | `evidence_471f09c2af52b4037acc3f6a` |
| [65] | `cdf:0:55` | 0.00126091 probability | `evidence_98d334fe8947554c4e899366` |
| [66] | `cdf:0:56` | 0.00149431 probability | `evidence_e33d4e68073bf46270cccef9` |
| [67] | `cdf:0:57` | 0.00175585 probability | `evidence_346655d3f8e05dbb7d7c7da8` |
| [68] | `cdf:0:58` | 0.00206607 probability | `evidence_e03491c7f391f4aa8b7e4cae` |
| [69] | `cdf:0:59` | 0.00243372 probability | `evidence_c63253bba167000d5034566f` |
| [70] | `cdf:0:60` | 0.00286362 probability | `evidence_be1a7f0240c1f2fe18709d20` |
| [71] | `cdf:0:61` | 0.00338192 probability | `evidence_8f5b14a1220dd5568918250a` |
| [72] | `cdf:0:62` | 0.00400378 probability | `evidence_4f88d9fb583ba05a34057795` |
| [73] | `cdf:0:63` | 0.00475683 probability | `evidence_70c55de0aa07c7e6c038caf9` |
| [74] | `cdf:0:64` | 0.00565969 probability | `evidence_ecd8cb50f150f151976ba795` |
| [75] | `cdf:0:65` | 0.0067716 probability | `evidence_3325441e824f9c7170546073` |
| [76] | `cdf:0:66` | 0.00812158 probability | `evidence_1bd054394a4071101fd05384` |
| [77] | `cdf:0:67` | 0.00979366 probability | `evidence_1550918f0c538f4861cc4606` |
| [78] | `cdf:0:68` | 0.0117993 probability | `evidence_2497dc1430a12b77c48e366a` |
| [79] | `cdf:0:69` | 0.0142777 probability | `evidence_550f1ffdedeaeb69091d5025` |
| [80] | `cdf:0:70` | 0.0171862 probability | `evidence_88cd6bac905860324c6de9b7` |
| [81] | `cdf:0:71` | 0.020687 probability | `evidence_32d6541123d712df7071a3b9` |
| [82] | `cdf:0:72` | 0.0250417 probability | `evidence_50043d2f31a0ab7678f73b8e` |
| [83] | `cdf:0:73` | 0.0303559 probability | `evidence_3dcf573023b56c0b07c4631d` |
| [84] | `cdf:0:74` | 0.0366797 probability | `evidence_66b3b9482e5b6674f30c8fcd` |
| [85] | `cdf:0:75` | 0.0442269 probability | `evidence_0d672a1c36841fad58fa4078` |
| [86] | `cdf:0:76` | 0.0534622 probability | `evidence_5b7191e4269a09dbd1724efd` |
| [87] | `cdf:0:77` | 0.0643305 probability | `evidence_43f7c25ce05da0d5eeb44846` |
| [88] | `cdf:0:78` | 0.0770617 probability | `evidence_17ac392a5582fb7122003cd3` |
| [89] | `cdf:0:79` | 0.0918921 probability | `evidence_e7b41b567e2099224d71b29b` |
| [90] | `cdf:0:80` | 0.108913 probability | `evidence_21e7c6ab7145752391458540` |
| [91] | `cdf:0:81` | 0.128388 probability | `evidence_597a6d2dc7806fcbbe450547` |
| [92] | `cdf:0:82` | 0.150542 probability | `evidence_e74fe23cb0c417f0843a31ec` |
| [93] | `cdf:0:83` | 0.175353 probability | `evidence_6c799c053cd9c1cf5cc4d72b` |
| [94] | `cdf:0:84` | 0.202906 probability | `evidence_91aef05c8a0e0055d5636691` |
| [95] | `cdf:0:85` | 0.233031 probability | `evidence_d659924af6b21a2e0155d87c` |
| [96] | `cdf:0:86` | 0.26607 probability | `evidence_f61090e45ac349ca28e7d1a5` |
| [97] | `cdf:0:87` | 0.301627 probability | `evidence_ad635e79587500e2f3429b48` |
| [98] | `cdf:0:88` | 0.339252 probability | `evidence_9546a748a4574c74df06e9a4` |
| [99] | `cdf:0:89` | 0.378827 probability | `evidence_90df9f3d44bf6af3fdd2ebc0` |
| [100] | `cdf:0:90` | 0.419596 probability | `evidence_a73e93c5b9d2cf3669eea9a9` |
| [101] | `cdf:0:91` | 0.461478 probability | `evidence_55ea6bc65ab8306edad5bac8` |
| [102] | `cdf:0:92` | 0.504292 probability | `evidence_b95c6e68b1a57ac82892094e` |
| [103] | `cdf:0:93` | 0.547482 probability | `evidence_98949558194cb9f33f191e4b` |
| [104] | `cdf:0:94` | 0.589294 probability | `evidence_037cad51cf4cd2586d11a25a` |
| [105] | `cdf:0:95` | 0.630147 probability | `evidence_06a239f66a1f9c350c1eeb44` |
| [106] | `cdf:0:96` | 0.669262 probability | `evidence_b9d263ed35f92ff7705ab30f` |
| [107] | `cdf:0:97` | 0.706505 probability | `evidence_920bf51acfc427fc1158371a` |
| [108] | `cdf:0:98` | 0.741081 probability | `evidence_818b5afd32e6c624d44a6f24` |
| [109] | `cdf:0:99` | 0.773268 probability | `evidence_e3d6149e5e70bf93a6d8d56f` |
| [110] | `cdf:0:100` | 0.802342 probability | `evidence_9ec039419e7e2a90df7b3e7c` |
| [111] | `cdf:0:101` | 0.828569 probability | `evidence_f1fc46cc8b0929376dc3c93f` |
| [112] | `cdf:0:102` | 0.851829 probability | `evidence_f6dbcae2ffcdcfcb67ce4a04` |
| [113] | `cdf:0:103` | 0.872663 probability | `evidence_bef4fcba0dc787445366ea36` |
| [114] | `cdf:0:104` | 0.89119 probability | `evidence_00629ffc026b930df060dabd` |
| [115] | `cdf:0:105` | 0.907439 probability | `evidence_1edc4c368fbedaf34dcb46e2` |
| [116] | `cdf:0:106` | 0.921561 probability | `evidence_f2c5713d2ab649ad73afb893` |
| [117] | `cdf:0:107` | 0.933798 probability | `evidence_4a4a2e8db9249512ebb3ffd1` |
| [118] | `cdf:0:108` | 0.944318 probability | `evidence_c2356d6618c7d107f1f03fc1` |
| [119] | `cdf:0:109` | 0.953406 probability | `evidence_2a7b79a36714f047c90bcdf6` |
| [120] | `cdf:0:110` | 0.961147 probability | `evidence_bfa514da5a64755823866355` |
| [121] | `cdf:0:111` | 0.967778 probability | `evidence_caeae8988fc20e99f1606546` |
| [122] | `cdf:0:112` | 0.97326 probability | `evidence_9148dae10dfb2c4787a21b32` |
| [123] | `cdf:0:113` | 0.978025 probability | `evidence_27673adde974bf77a7e165da` |
| [124] | `cdf:0:114` | 0.981838 probability | `evidence_a215d11308249aa6fac0ad19` |
| [125] | `cdf:0:115` | 0.985049 probability | `evidence_90c5a2e67a6b67b5bf3f9a2b` |
| [126] | `cdf:0:116` | 0.9877 probability | `evidence_7c13c935d1e0d26bb602a8f0` |
| [127] | `cdf:0:117` | 0.989848 probability | `evidence_1b74a08886b5588ac561e2da` |
| [128] | `cdf:0:118` | 0.99171 probability | `evidence_c1c5060118c8957cef41115d` |
| [129] | `cdf:0:119` | 0.993245 probability | `evidence_ec46f683d5378bb267784246` |
| [130] | `cdf:0:120` | 0.994486 probability | `evidence_07d4008d3420509685c3a678` |
| [131] | `cdf:0:121` | 0.995511 probability | `evidence_5b945957a36c9aeb40ce1c5b` |
| [132] | `cdf:0:122` | 0.996363 probability | `evidence_377f8c6a56f8182a7168135d` |
| [133] | `cdf:0:123` | 0.997048 probability | `evidence_cb9c1711c6e44e133b48a60f` |
| [134] | `cdf:0:124` | 0.997614 probability | `evidence_ff45ea172017f06b4e5ea32b` |
| [135] | `cdf:0:125` | 0.998066 probability | `evidence_25f838072e6a6de3b598b3f1` |
| [136] | `cdf:0:126` | 0.998433 probability | `evidence_eef1fc4f67b0c1d5e9dd9ffc` |
| [137] | `cdf:0:127` | 0.998732 probability | `evidence_3169b90c3d5e129bfdf944ed` |
| [138] | `cdf:0:128` | 0.998973 probability | `evidence_e22175e3bf58af4420c1aa01` |
| [139] | `cdf:0:129` | 0.999168 probability | `evidence_0a8654e9a9b85f8a68e78894` |
| [140] | `cdf:0:130` | 0.999321 probability | `evidence_baa156380d1f3d35664b0d22` |
| [141] | `cdf:0:131` | 0.999445 probability | `evidence_12aa6d22b07859015215ea60` |
| [142] | `cdf:0:132` | 0.999544 probability | `evidence_04bfa68106e80f493b3720ad` |
| [143] | `cdf:0:133` | 0.999627 probability | `evidence_53ab471f5e172826780eaf9b` |
| [144] | `cdf:0:134` | 0.999695 probability | `evidence_7c8f7d1455744b97ceb3b2d1` |
| [145] | `cdf:0:135` | 0.99975 probability | `evidence_c7b3aaa8762a2aaf95679769` |
| [146] | `cdf:0:136` | 0.999793 probability | `evidence_3abedb36c0603b64d0c3d588` |
| [147] | `cdf:0:137` | 0.999829 probability | `evidence_eabe230faddb354c2724924f` |
| [148] | `cdf:0:138` | 0.999858 probability | `evidence_d2d4cfb87e20510483b90d7c` |
| [149] | `cdf:0:139` | 0.999882 probability | `evidence_7311e099f56ba99a76751cf4` |
| [150] | `cdf:0:140` | 0.999901 probability | `evidence_bf3e43d4013a86ccef2c9400` |
| [151] | `cdf:0:141` | 0.999916 probability | `evidence_4f2512a0197df527375104f7` |
| [152] | `cdf:0:142` | 0.999929 probability | `evidence_e733b3207a20a5936911db81` |
| [153] | `cdf:0:143` | 0.99994 probability | `evidence_8d9a5b792f2f45fb1befa7c2` |
| [154] | `cdf:0:144` | 0.999948 probability | `evidence_5e1d6befa72b8436d17f8933` |
| [155] | `cdf:0:145` | 0.999956 probability | `evidence_5b17dfb7f6ebd6b6e77ecfce` |
| [156] | `cdf:0:146` | 0.999962 probability | `evidence_8b517435b53e0d2b60e92351` |
| [157] | `cdf:0:147` | 0.999967 probability | `evidence_cdfb0bb2c5b0b009d22a9bfa` |
| [158] | `cdf:0:148` | 0.999971 probability | `evidence_70e4ae9f7f9dc1a44c26097c` |
| [159] | `cdf:0:149` | 0.999975 probability | `evidence_c4329875841ddd6db1460731` |
| [160] | `cdf:0:150` | 0.999977 probability | `evidence_d4ce27179183c2b1d79601a1` |
| [161] | `cdf:0:151` | 0.99998 probability | `evidence_aac516f575eb434d6bef29a0` |
| [162] | `cdf:0:152` | 0.999982 probability | `evidence_801f214354edc42479e30b1d` |
| [163] | `cdf:0:153` | 0.999984 probability | `evidence_b55959504d87ac9cc877665e` |
| [164] | `cdf:0:154` | 0.999985 probability | `evidence_fa3ebb68bf8f61554971a80c` |
| [165] | `cdf:0:155` | 0.999987 probability | `evidence_6919e15b4408ba5ea2631178` |
| [166] | `cdf:0:156` | 0.999988 probability | `evidence_9a1bde5f79fc1e824732075a` |
| [167] | `cdf:0:157` | 0.999989 probability | `evidence_17da5631edce3769c8c81d97` |
| [168] | `cdf:0:158` | 0.99999 probability | `evidence_f4c88dac02fb82b52921522a` |
| [169] | `cdf:0:159` | 0.999991 probability | `evidence_31040b2479871b41b9bfa6a6` |
| [170] | `cdf:0:160` | 0.999992 probability | `evidence_a1a13a9e38b61c0da7634886` |
| [171] | `cdf:1:0` | 7.34422e-06 probability | `evidence_c1b3d2061b5e360b52176b43` |
| [172] | `cdf:1:1` | 8.12266e-06 probability | `evidence_6b5eb22c2a311b140caa9b64` |
| [173] | `cdf:1:2` | 8.99452e-06 probability | `evidence_4ae84442dbdb34b338726f53` |
| [174] | `cdf:1:3` | 9.97709e-06 probability | `evidence_e1b85c76a234b859c39daa01` |
| [175] | `cdf:1:4` | 1.10804e-05 probability | `evidence_bcea5e39fae46cb0f3cd7d7d` |
| [176] | `cdf:1:5` | 1.23243e-05 probability | `evidence_4806c097987ec60c3ec6155f` |
| [177] | `cdf:1:6` | 1.3721e-05 probability | `evidence_b47ee31eed23ac0d2419991d` |
| [178] | `cdf:1:7` | 1.52986e-05 probability | `evidence_e9d97ef3dacbe31a70d52e77` |
| [179] | `cdf:1:8` | 1.70482e-05 probability | `evidence_eafd6e260265de8a06808bdb` |
| [180] | `cdf:1:9` | 1.90646e-05 probability | `evidence_8093cfedaae3e2c9ae693d2c` |
| [181] | `cdf:1:10` | 2.14734e-05 probability | `evidence_5da099437bb62508a022ccf8` |
| [182] | `cdf:1:11` | 2.4322e-05 probability | `evidence_a0feabdf0bcfdfeb59263680` |
| [183] | `cdf:1:12` | 2.75607e-05 probability | `evidence_d4306e9a51bd3242b150789e` |
| [184] | `cdf:1:13` | 3.15028e-05 probability | `evidence_e30879772ed28cbae3ae3c7e` |
| [185] | `cdf:1:14` | 3.62575e-05 probability | `evidence_779f093ddb10e2abdb64d34b` |
| [186] | `cdf:1:15` | 4.20623e-05 probability | `evidence_2cb2cd316a69ac8746da9c2b` |
| [187] | `cdf:1:16` | 4.89001e-05 probability | `evidence_c4992823248e1c085e490100` |
| [188] | `cdf:1:17` | 5.71665e-05 probability | `evidence_67da56c1a2c868b055583eba` |
| [189] | `cdf:1:18` | 6.74787e-05 probability | `evidence_c5f2982e6410ea92f63a0981` |
| [190] | `cdf:1:19` | 7.94454e-05 probability | `evidence_e5899e1fb55254bb29f88b91` |
| [191] | `cdf:1:20` | 9.35418e-05 probability | `evidence_e7125e3b9cc0d82a14430b9b` |
| [192] | `cdf:1:21` | 0.00011111 probability | `evidence_ac8d01dd0c71a2110256fc3b` |
| [193] | `cdf:1:22` | 0.00013278 probability | `evidence_c2864734ce3d227857423306` |
| [194] | `cdf:1:23` | 0.000158034 probability | `evidence_f3c813d340aa4fd4583656b6` |
| [195] | `cdf:1:24` | 0.000189802 probability | `evidence_6f0203958e9b3290a2e5624d` |
| [196] | `cdf:1:25` | 0.00022758 probability | `evidence_cba9b375e0abd1fd7581795e` |
| [197] | `cdf:1:26` | 0.000273915 probability | `evidence_37cf053feec819c5f2b6661a` |
| [198] | `cdf:1:27` | 0.000328683 probability | `evidence_5d3797435f7a632b9f51cf8a` |
| [199] | `cdf:1:28` | 0.000394532 probability | `evidence_e5bd915934bec5f2e673dbd6` |
| [200] | `cdf:1:29` | 0.000474756 probability | `evidence_972bdaa639d21f79ef1be07a` |
| [201] | `cdf:1:30` | 0.000569407 probability | `evidence_346c212d5fb1d239bc93e835` |
| [202] | `cdf:1:31` | 0.000683338 probability | `evidence_12d7ff6595a8ab5db5a5fbb7` |
| [203] | `cdf:1:32` | 0.000822 probability | `evidence_d88707995537a53c87952c63` |
| [204] | `cdf:1:33` | 0.000980171 probability | `evidence_1371880c839cb9e05436200f` |
| [205] | `cdf:1:34` | 0.00117447 probability | `evidence_7e33e2e221d9e35c1d8b9e90` |
| [206] | `cdf:1:35` | 0.00140271 probability | `evidence_87c34ca0e6130574e64a58a8` |
| [207] | `cdf:1:36` | 0.00167748 probability | `evidence_7f0f1db38fa97c3f3cd0245a` |
| [208] | `cdf:1:37` | 0.00200115 probability | `evidence_1e9080b1dee76bb9c61ad2a2` |
| [209] | `cdf:1:38` | 0.00237949 probability | `evidence_4a750ffe279bccaafeb7727c` |
| [210] | `cdf:1:39` | 0.00282383 probability | `evidence_22c349b2366ad9b833514893` |
| [211] | `cdf:1:40` | 0.00334114 probability | `evidence_6dc4dda8dfcec8739a0b3840` |
| [212] | `cdf:1:41` | 0.00394224 probability | `evidence_2d5faec18c61da757ba475c4` |
| [213] | `cdf:1:42` | 0.00462726 probability | `evidence_62569740206665f4c20f8dbf` |
| [214] | `cdf:1:43` | 0.00543665 probability | `evidence_60d2378d5177706f80e92719` |
| [215] | `cdf:1:44` | 0.00636056 probability | `evidence_1339c72bf6d1374734a8e8c9` |
| [216] | `cdf:1:45` | 0.00736757 probability | `evidence_7a42ab92ffc6232bde8acc1b` |
| [217] | `cdf:1:46` | 0.00855267 probability | `evidence_44069e332adcca6477f705a0` |
| [218] | `cdf:1:47` | 0.0099238 probability | `evidence_bd4100bfbc501c872022a44d` |
| [219] | `cdf:1:48` | 0.0114849 probability | `evidence_1e350edc18a9d4e8878d5be5` |
| [220] | `cdf:1:49` | 0.0132933 probability | `evidence_ec9811017a99c9ddf66208e6` |
| [221] | `cdf:1:50` | 0.0153196 probability | `evidence_c696106dd7c87fa39baab415` |
| [222] | `cdf:1:51` | 0.0176659 probability | `evidence_63af9b5b89bbc282ab59286b` |
| [223] | `cdf:1:52` | 0.0202035 probability | `evidence_47c60a0f9400530d274f7c21` |
| [224] | `cdf:1:53` | 0.0232088 probability | `evidence_54ac97babbd18910646306fb` |
| [225] | `cdf:1:54` | 0.0266057 probability | `evidence_eb37578ef779b1aea1368e4d` |
| [226] | `cdf:1:55` | 0.0306673 probability | `evidence_0f077fd603d92e809ddc16dc` |
| [227] | `cdf:1:56` | 0.0355583 probability | `evidence_d8ce96adac2c7d100a971c2e` |
| [228] | `cdf:1:57` | 0.0409903 probability | `evidence_27d1a60f1946b28ffc0f19c8` |
| [229] | `cdf:1:58` | 0.0472781 probability | `evidence_43d5cb46be3a4a9882de407b` |
| [230] | `cdf:1:59` | 0.0543991 probability | `evidence_f08516b16be2eab7a08a95be` |
| [231] | `cdf:1:60` | 0.0627213 probability | `evidence_6645b0720aeee2994d25ea69` |
| [232] | `cdf:1:61` | 0.0721324 probability | `evidence_3c5dbe131324f8b444be8232` |
| [233] | `cdf:1:62` | 0.082466 probability | `evidence_d44e9f4df237dcf8b0efc16b` |
| [234] | `cdf:1:63` | 0.094086 probability | `evidence_7afb08073fef1e014df099ac` |
| [235] | `cdf:1:64` | 0.107303 probability | `evidence_ae9f512ef1efcddb08ce7fd8` |
| [236] | `cdf:1:65` | 0.122226 probability | `evidence_2d987ae8aa294bd22ff16a94` |
| [237] | `cdf:1:66` | 0.139068 probability | `evidence_ae3f2072f660a61f7e1ea7d8` |
| [238] | `cdf:1:67` | 0.158048 probability | `evidence_6575f6e746c420ca2a527a38` |
| [239] | `cdf:1:68` | 0.179174 probability | `evidence_b25efa528d908788768ea3b3` |
| [240] | `cdf:1:69` | 0.202208 probability | `evidence_2d7c5beca956e25c632bcb0a` |
| [241] | `cdf:1:70` | 0.226728 probability | `evidence_e15b09da2753efb14fe2ad05` |
| [242] | `cdf:1:71` | 0.253368 probability | `evidence_f4cfd8e7919a530908ce6272` |
| [243] | `cdf:1:72` | 0.283046 probability | `evidence_c9efa35377af4843805b9d3a` |
| [244] | `cdf:1:73` | 0.315398 probability | `evidence_ebe35141f5922c51d060382b` |
| [245] | `cdf:1:74` | 0.349627 probability | `evidence_6562d2d1ed31424a979395e9` |
| [246] | `cdf:1:75` | 0.385355 probability | `evidence_d24bffb5ee2925bf63c19fef` |
| [247] | `cdf:1:76` | 0.423421 probability | `evidence_65a7eefeae7b57010a2a42d5` |
| [248] | `cdf:1:77` | 0.462695 probability | `evidence_e8135d203ba997953873e3b6` |
| [249] | `cdf:1:78` | 0.50236 probability | `evidence_908a17b5886ce28dba22c604` |
| [250] | `cdf:1:79` | 0.542339 probability | `evidence_633645ac043a058547600429` |
| [251] | `cdf:1:80` | 0.581765 probability | `evidence_22c5c420965998b53b897a1f` |
| [252] | `cdf:1:81` | 0.620757 probability | `evidence_0c21fdce2932b9961aa3ec91` |
| [253] | `cdf:1:82` | 0.658961 probability | `evidence_c2361259d96b3587847b76df` |
| [254] | `cdf:1:83` | 0.695324 probability | `evidence_138fb9e17261e312579cd86d` |
| [255] | `cdf:1:84` | 0.729638 probability | `evidence_3564f10f8e3c0706c3ec0ef3` |
| [256] | `cdf:1:85` | 0.761738 probability | `evidence_f49b49e99f65b344a5db298c` |
| [257] | `cdf:1:86` | 0.792191 probability | `evidence_a69799f2272c15f56ce68a07` |
| [258] | `cdf:1:87` | 0.820257 probability | `evidence_2a73b7d1be904485880888e2` |
| [259] | `cdf:1:88` | 0.845746 probability | `evidence_ed8267c510e49e660fcedd7e` |
| [260] | `cdf:1:89` | 0.868518 probability | `evidence_375fb08786e3c794b172b133` |
| [261] | `cdf:1:90` | 0.888624 probability | `evidence_57b13ed9ef1d0c180512266e` |
| [262] | `cdf:1:91` | 0.90661 probability | `evidence_241ba120ef3511287fa960be` |
| [263] | `cdf:1:92` | 0.922205 probability | `evidence_3a9c7628ce8d8731575b94ce` |
| [264] | `cdf:1:93` | 0.935722 probability | `evidence_949487031db8cbdb8e0d57fa` |
| [265] | `cdf:1:94` | 0.946986 probability | `evidence_c2418b41b1701e66cf78176d` |
| [266] | `cdf:1:95` | 0.956556 probability | `evidence_cbffa10d52b2f06e413f671a` |
| [267] | `cdf:1:96` | 0.964609 probability | `evidence_bec6584b92611609f4d60520` |
| [268] | `cdf:1:97` | 0.971302 probability | `evidence_16be338d37eb10e017b8c2ea` |
| [269] | `cdf:1:98` | 0.976746 probability | `evidence_f5eff384619931ce2e38874e` |
| [270] | `cdf:1:99` | 0.981135 probability | `evidence_5bacbb9cdf7cbc9795ddd087` |
| [271] | `cdf:1:100` | 0.984669 probability | `evidence_10249502655ce91565c104be` |
| [272] | `cdf:1:101` | 0.98752 probability | `evidence_53d0f7a9584dc2df979e3aee` |
| [273] | `cdf:1:102` | 0.989899 probability | `evidence_19d1614fa46880b35df445d8` |
| [274] | `cdf:1:103` | 0.991809 probability | `evidence_a03955994c36fd7d6f5da3ea` |
| [275] | `cdf:1:104` | 0.993327 probability | `evidence_70f55176ad2c7d7566e374cf` |
| [276] | `cdf:1:105` | 0.994587 probability | `evidence_907c57b32c0eae01b91f0ee4` |
| [277] | `cdf:1:106` | 0.995633 probability | `evidence_9c06dd764eac6fbc96cd722f` |
| [278] | `cdf:1:107` | 0.996475 probability | `evidence_687dbb88e5d85dd5c72bffed` |
| [279] | `cdf:1:108` | 0.997144 probability | `evidence_62f31a09ee531a01b1d4b766` |
| [280] | `cdf:1:109` | 0.997673 probability | `evidence_5aafe14ad46f83d846e46149` |
| [281] | `cdf:1:110` | 0.998105 probability | `evidence_41c6c0dd2cee2514de5f9e34` |
| [282] | `cdf:1:111` | 0.998443 probability | `evidence_7f53e822da0e835fcf653781` |
| [283] | `cdf:1:112` | 0.998711 probability | `evidence_689663a7538e138505f1913e` |
| [284] | `cdf:1:113` | 0.998935 probability | `evidence_8597cfb35e8c477fc104a397` |
| [285] | `cdf:1:114` | 0.999111 probability | `evidence_b1a28704f14f8e8c059ffd09` |
| [286] | `cdf:1:115` | 0.999255 probability | `evidence_d52c6d2be52671a9e74cffe5` |
| [287] | `cdf:1:116` | 0.999376 probability | `evidence_b0dc3d1af02fd7b95549aa94` |
| [288] | `cdf:1:117` | 0.999479 probability | `evidence_cbc15f4563309245f1ce4d48` |
| [289] | `cdf:1:118` | 0.999565 probability | `evidence_4f96755d1aa4d68f0111c5ef` |
| [290] | `cdf:1:119` | 0.999638 probability | `evidence_c1449cd8fbf13afde58c6953` |
| [291] | `cdf:1:120` | 0.999698 probability | `evidence_76fd7782d9c46f8a30c77eb4` |
| [292] | `cdf:1:121` | 0.999747 probability | `evidence_026012020938dfa342f3d372` |
| [293] | `cdf:1:122` | 0.999789 probability | `evidence_0fe4e0f3463a547bcc079330` |
| [294] | `cdf:1:123` | 0.999823 probability | `evidence_85b2c0f00291d7c6de96880e` |
| [295] | `cdf:1:124` | 0.999851 probability | `evidence_8dfeff492329b4fcbaedeab7` |
| [296] | `cdf:1:125` | 0.999875 probability | `evidence_e335ce2834534d49069640c1` |
| [297] | `cdf:1:126` | 0.999893 probability | `evidence_7512540b2468e9d356c58884` |
| [298] | `cdf:1:127` | 0.999909 probability | `evidence_d2544d3e2cf6e687ea54dd4a` |
| [299] | `cdf:1:128` | 0.999921 probability | `evidence_9785c3d28796f8620112fad2` |
| [300] | `cdf:1:129` | 0.999933 probability | `evidence_a32b327989112fe6a7357c26` |
| [301] | `cdf:1:130` | 0.999942 probability | `evidence_3de4b577b074fefab0961a10` |
| [302] | `cdf:1:131` | 0.99995 probability | `evidence_8ab10b6a6f75fc7410a8d482` |
| [303] | `cdf:1:132` | 0.999957 probability | `evidence_4e0dd26d0c0fa30d67f17825` |
| [304] | `cdf:1:133` | 0.999963 probability | `evidence_8b5a972a1375946fedcc336e` |
| [305] | `cdf:1:134` | 0.999968 probability | `evidence_65ddf1002920cd05dbbf8514` |
| [306] | `cdf:1:135` | 0.999972 probability | `evidence_b353e963de8b72d69fe8619e` |
| [307] | `cdf:1:136` | 0.999976 probability | `evidence_6baa5a412286036d71316a04` |
| [308] | `cdf:1:137` | 0.999979 probability | `evidence_85bda58a66f0262e213ac6c1` |
| [309] | `cdf:1:138` | 0.999981 probability | `evidence_31276ebaa51cdb6476590043` |
| [310] | `cdf:1:139` | 0.999983 probability | `evidence_821e1a84250f4bdcfb2e1a14` |
| [311] | `cdf:1:140` | 0.999985 probability | `evidence_b28b7bc7891fc28eec0c04c8` |
| [312] | `cdf:1:141` | 0.999987 probability | `evidence_fd8c0c5ee0bf637fa500e6cb` |
| [313] | `cdf:1:142` | 0.999988 probability | `evidence_421b386af381d8211eb66f6d` |
| [314] | `cdf:1:143` | 0.999989 probability | `evidence_38a521ab6fc4af8ef4733fe4` |
| [315] | `cdf:1:144` | 0.99999 probability | `evidence_dd58ef2403e4bbbc5fac5dc9` |
| [316] | `cdf:1:145` | 0.999991 probability | `evidence_35d2e95632b78028ff83fd25` |
| [317] | `cdf:1:146` | 0.999992 probability | `evidence_4f8e9ae75ed8acecb1ab0f69` |
| [318] | `cdf:1:147` | 0.999993 probability | `evidence_23815a1ac29b7d515c8da482` |
| [319] | `cdf:1:148` | 0.999994 probability | `evidence_5e60454034d22fabafc1d58f` |
| [320] | `cdf:1:149` | 0.999994 probability | `evidence_c965ab4c33ea0360104def5f` |
| [321] | `cdf:1:150` | 0.999995 probability | `evidence_5237b745ff93fe7576978532` |
| [322] | `cdf:1:151` | 0.999995 probability | `evidence_00f42e7b10963a08a80a1f59` |
| [323] | `cdf:1:152` | 0.999995 probability | `evidence_9544e6851cd7bba63eeeae65` |
| [324] | `cdf:1:153` | 0.999996 probability | `evidence_3cd8a9b1453f9034e6dc1dcd` |
| [325] | `cdf:1:154` | 0.999996 probability | `evidence_5b67b19011eb1a4b66bfff66` |
| [326] | `cdf:1:155` | 0.999996 probability | `evidence_72e3dc0199fe54b0001c7f30` |
| [327] | `cdf:1:156` | 0.999997 probability | `evidence_7df18954bda3cbdc0ef20864` |
| [328] | `cdf:1:157` | 0.999997 probability | `evidence_da56cc94cbe19766b6bbc610` |
| [329] | `cdf:1:158` | 0.999997 probability | `evidence_027099fdc63812f4cbbec467` |
| [330] | `cdf:1:159` | 0.999997 probability | `evidence_6889e9d625de6674e02933e1` |
| [331] | `cdf:1:160` | 0.999997 probability | `evidence_41abcf154c3e18409342ee69` |
| [332] | `density:0:0` | 2.35241e-07 probability density | `evidence_943c317e3b56dd56ac7d589d` |
| [333] | `density:0:1` | 2.44849e-07 probability density | `evidence_e5deaa5bf2a71cb76df0e266` |
| [334] | `density:0:2` | 2.60779e-07 probability density | `evidence_133933707cb92f285be67859` |
| [335] | `density:0:3` | 2.74251e-07 probability density | `evidence_6c35675b54a1e0be7f4b2a8d` |
| [336] | `density:0:4` | 2.93808e-07 probability density | `evidence_3c9f0396d2834bfe1a1d43e6` |
| [337] | `density:0:5` | 3.08457e-07 probability density | `evidence_d2e43f40fba837cb98706807` |
| [338] | `density:0:6` | 3.41794e-07 probability density | `evidence_2d9c0669cc54759f4760fd05` |
| [339] | `density:0:7` | 3.69527e-07 probability density | `evidence_ceca4ca2b1fd4c3d4b8b57f7` |
| [340] | `density:0:8` | 4.01058e-07 probability density | `evidence_194896aa703debb0cdc5c366` |
| [341] | `density:0:9` | 4.55799e-07 probability density | `evidence_4053a8dfa70fcf1895c84d5b` |
| [342] | `density:0:10` | 4.86891e-07 probability density | `evidence_8bf147581bb1ffed0e00e66b` |
| [343] | `density:0:11` | 5.29905e-07 probability density | `evidence_7ddb3bf7bf45504526455081` |
| [344] | `density:0:12` | 6.10129e-07 probability density | `evidence_d687c86c78ea0f99b3e64b8d` |
| [345] | `density:0:13` | 6.93821e-07 probability density | `evidence_df1ea76baf6c62e092e8caf8` |
| [346] | `density:0:14` | 8.09025e-07 probability density | `evidence_5be0634a99fc4c81d85d972a` |
| [347] | `density:0:15` | 8.72157e-07 probability density | `evidence_8d7159f927c632acd3d9e820` |
| [348] | `density:0:16` | 1.00371e-06 probability density | `evidence_215d8460118827f54e52d2bf` |
| [349] | `density:0:17` | 1.16407e-06 probability density | `evidence_7fbce221c75c54d08a37c17f` |
| [350] | `density:0:18` | 1.3088e-06 probability density | `evidence_3d62a3776910d56ffcc722e3` |
| [351] | `density:0:19` | 1.48246e-06 probability density | `evidence_707ed29a0dae6030db9ea77d` |
| [352] | `density:0:20` | 1.71966e-06 probability density | `evidence_6f8cf58ba00f861465549f77` |
| [353] | `density:0:21` | 1.97735e-06 probability density | `evidence_b3cb47d0913a77a60a39a3cf` |
| [354] | `density:0:22` | 2.28649e-06 probability density | `evidence_71cd6d1617503a131c799d7d` |
| [355] | `density:0:23` | 2.60862e-06 probability density | `evidence_a16bd90cb55f3b0e9c9df3a4` |
| [356] | `density:0:24` | 3.00405e-06 probability density | `evidence_bb6ee2b7c97b55b0b5b6c287` |
| [357] | `density:0:25` | 3.48363e-06 probability density | `evidence_96b6586bf748d53c68e7a71a` |
| [358] | `density:0:26` | 3.91288e-06 probability density | `evidence_dbc1f653b83e618f6f179ca1` |
| [359] | `density:0:27` | 4.40482e-06 probability density | `evidence_b9c301eafe89c51eb74eff0a` |
| [360] | `density:0:28` | 5.04999e-06 probability density | `evidence_6b7ff5c9ec4eb4d9a8b59c06` |
| [361] | `density:0:29` | 5.64817e-06 probability density | `evidence_1f364843a2f7c4b48794c391` |
| [362] | `density:0:30` | 6.32602e-06 probability density | `evidence_c36e5ff5971fbbe0c3fe9d0e` |
| [363] | `density:0:31` | 7.44665e-06 probability density | `evidence_cffe0aaa14c76c906624cee3` |
| [364] | `density:0:32` | 8.28445e-06 probability density | `evidence_b03fc65f248d695af511eeea` |
| [365] | `density:0:33` | 9.8269e-06 probability density | `evidence_d22674f32b2b668891a8e01a` |
| [366] | `density:0:34` | 1.11834e-05 probability density | `evidence_44fcb5c80e77054d9108cee2` |
| [367] | `density:0:35` | 1.30767e-05 probability density | `evidence_c32dc7be3b1fbb47fd7e40e8` |
| [368] | `density:0:36` | 1.52608e-05 probability density | `evidence_20dc6b3e7e0e30b74ddf5fdb` |
| [369] | `density:0:37` | 1.76997e-05 probability density | `evidence_6842909cdeb0884422db3e1d` |
| [370] | `density:0:38` | 2.0054e-05 probability density | `evidence_aaba428f35506c8bb45ae492` |
| [371] | `density:0:39` | 2.25706e-05 probability density | `evidence_4cff1fc04632386d2636fb8c` |
| [372] | `density:0:40` | 2.58296e-05 probability density | `evidence_d67d31fb869c6a9d792d72ed` |
| [373] | `density:0:41` | 2.85767e-05 probability density | `evidence_ccd9676a0c966dd05130dec3` |
| [374] | `density:0:42` | 3.36578e-05 probability density | `evidence_8608615a1b4bb526d10eb5d8` |
| [375] | `density:0:43` | 3.88921e-05 probability density | `evidence_7a54b345c1ea7f2b367f1fba` |
| [376] | `density:0:44` | 4.28874e-05 probability density | `evidence_fbfabcc98277b4773c206c5b` |
| [377] | `density:0:45` | 4.95986e-05 probability density | `evidence_30efca1c0dee94278486866d` |
| [378] | `density:0:46` | 5.70684e-05 probability density | `evidence_1d0e732e7ebcd20355287942` |
| [379] | `density:0:47` | 6.63035e-05 probability density | `evidence_f207b69792ebb82cfc9a3f46` |
| [380] | `density:0:48` | 7.78141e-05 probability density | `evidence_2e3801aa8b6e4e63d52364ab` |
| [381] | `density:0:49` | 8.97818e-05 probability density | `evidence_a58c7f81a056949c570a12a1` |
| [382] | `density:0:50` | 0.000105599 probability density | `evidence_bca8e5d985a9bf216404016a` |
| [383] | `density:0:51` | 0.000117059 probability density | `evidence_088571c28d182b7498eb125b` |
| [384] | `density:0:52` | 0.000133996 probability density | `evidence_e50506dc6c9aeed10fd26011` |
| [385] | `density:0:53` | 0.000149536 probability density | `evidence_99e7a5565032cecc81a6fd42` |
| [386] | `density:0:54` | 0.000187587 probability density | `evidence_8fcdc334e2f17357480e8f71` |
| [387] | `density:0:55` | 0.000229668 probability density | `evidence_d9e08543928cd9c86f3506b1` |
| [388] | `density:0:56` | 0.000253575 probability density | `evidence_6a1ef0a6583df4c66574c12d` |
| [389] | `density:0:57` | 0.000296372 probability density | `evidence_c52a18f36efcfe0f4bc3b31a` |
| [390] | `density:0:58` | 0.000346075 probability density | `evidence_45457879da26e659466054e2` |
| [391] | `density:0:59` | 0.000398734 probability density | `evidence_ba5d0e2f703946569f104717` |
| [392] | `density:0:60` | 0.00047368 probability density | `evidence_3628b3ad44a4db0c8e34b024` |
| [393] | `density:0:61` | 0.000559994 probability density | `evidence_8d3b4275baeaacc46af03f60` |
| [394] | `density:0:62` | 0.00066817 probability density | `evidence_9d0405d8952864e2b3621fc7` |
| [395] | `density:0:63` | 0.000789352 probability density | `evidence_88c62ea08036602649976b92` |
| [396] | `density:0:64` | 0.000957857 probability density | `evidence_64b492ddb4503e9768a8ae46` |
| [397] | `density:0:65` | 0.00114588 probability density | `evidence_057b56909f2ac7cfb83b7f26` |
| [398] | `density:0:66` | 0.00139847 probability density | `evidence_d06948cace61482231f9a360` |
| [399] | `density:0:67` | 0.00165281 probability density | `evidence_7011f39eb82ad8341b9b081b` |
| [400] | `density:0:68` | 0.00201246 probability density | `evidence_a39e32179a07b95e1bff1ddf` |
| [401] | `density:0:69` | 0.00232708 probability density | `evidence_96e29c2fbab45d1bdc014377` |
| [402] | `density:0:70` | 0.00275987 probability density | `evidence_841fecb80bfcb24afc9a3d1e` |
| [403] | `density:0:71` | 0.00338277 probability density | `evidence_c17f9bdd2dfbaf69147489ff` |
| [404] | `density:0:72` | 0.00406741 probability density | `evidence_422d076d0e5ea2a29bc096fd` |
| [405] | `density:0:73` | 0.00476924 probability density | `evidence_c17a517926a5fba1fe7abd52` |
| [406] | `density:0:74` | 0.0056084 probability density | `evidence_1cb423c017dff2ed4efd5685` |
| [407] | `density:0:75` | 0.00676214 probability density | `evidence_44fbe6dc4ddd344b8fb41a2d` |
| [408] | `density:0:76` | 0.00784108 probability density | `evidence_7d620c531345c232a1d1a70e` |
| [409] | `density:0:77` | 0.00905034 probability density | `evidence_3a74c7462ca1a9f6b00aa419` |
| [410] | `density:0:78` | 0.010388 probability density | `evidence_e7667863596dca7ea5b2bc84` |
| [411] | `density:0:79` | 0.0117471 probability density | `evidence_1a55647e2213d97912f0ec87` |
| [412] | `density:0:80` | 0.0132445 probability density | `evidence_e7c81ab40cdfa87fcfacc3ae` |
| [413] | `density:0:81` | 0.0148446 probability density | `evidence_6cfabe007053d5a24b637b1a` |
| [414] | `density:0:82` | 0.0163814 probability density | `evidence_94745e83f895c3ccc120842f` |
| [415] | `density:0:83` | 0.0179254 probability density | `evidence_73e5c26b3202bc8f579406f3` |
| [416] | `density:0:84` | 0.0193102 probability density | `evidence_6daa0c707f0706f58c7279d4` |
| [417] | `density:0:85` | 0.0208683 probability density | `evidence_d89aa49ba26bc97323724c18` |
| [418] | `density:0:86` | 0.0221284 probability density | `evidence_1e28fff397c0a171087aa3dc` |
| [419] | `density:0:87` | 0.0230725 probability density | `evidence_b58bf5e7e463e5cadd242400` |
| [420] | `density:0:88` | 0.0239123 probability density | `evidence_460a3e471e3e3edf1270e190` |
| [421] | `density:0:89` | 0.0242721 probability density | `evidence_bdec46616da2b3190d567f2e` |
| [422] | `density:0:90` | 0.0245695 probability density | `evidence_aced86fb1cd735a7873522fe` |
| [423] | `density:0:91` | 0.0247471 probability density | `evidence_8549556ad0b0e0ae729bc2dc` |
| [424] | `density:0:92` | 0.0245987 probability density | `evidence_f7bc0b014da79d39327b5302` |
| [425] | `density:0:93` | 0.023464 probability density | `evidence_b5d51c055e07e239732b3dec` |
| [426] | `density:0:94` | 0.0225901 probability density | `evidence_70cb164c0f9b0d1a5d128be5` |
| [427] | `density:0:95` | 0.0213117 probability density | `evidence_33e58a37643f08c3759e2406` |
| [428] | `density:0:96` | 0.0199937 probability density | `evidence_c69838226a4dd83b5bdecfd6` |
| [429] | `density:0:97` | 0.0182897 probability density | `evidence_d298c739eafb5b76b2d2ad2a` |
| [430] | `density:0:98` | 0.0167767 probability density | `evidence_bddcc36d53b395019d13a02d` |
| [431] | `density:0:99` | 0.0149314 probability density | `evidence_fada4dfb6115b3109fb23ae4` |
| [432] | `density:0:100` | 0.0132719 probability density | `evidence_44b4cfce42bcd5aa404e5432` |
| [433] | `density:0:101` | 0.0115978 probability density | `evidence_f103f845461ceee55269d1d7` |
| [434] | `density:0:102` | 0.0102359 probability density | `evidence_d98e1a31e240de593b9b9465` |
| [435] | `density:0:103` | 0.00896862 probability density | `evidence_fefa69a00b3819dca35c675b` |
| [436] | `density:0:104` | 0.00775067 probability density | `evidence_0774538467474321092dcb0b` |
| [437] | `density:0:105` | 0.00663713 probability density | `evidence_e2fee6632714b459af91ec78` |
| [438] | `density:0:106` | 0.00566695 probability density | `evidence_185409dc43b7f9f2a8aef926` |
| [439] | `density:0:107` | 0.00480015 probability density | `evidence_468946c754a1cfb932f19d84` |
| [440] | `density:0:108` | 0.00408625 probability density | `evidence_42bfb1b3dc3ee48a33df4e05` |
| [441] | `density:0:109` | 0.0034292 probability density | `evidence_af29b94a2cb832dfe8b56507` |
| [442] | `density:0:110` | 0.00289489 probability density | `evidence_1ef1ae63a1c0a04dd21eabfb` |
| [443] | `density:0:111` | 0.00235763 probability density | `evidence_cd127b3edf534ae77c886fc3` |
| [444] | `density:0:112` | 0.00201963 probability density | `evidence_156d5f3c76b97c0a00a6d652` |
| [445] | `density:0:113` | 0.00159199 probability density | `evidence_db2b506de3318b7e0d9e52be` |
| [446] | `density:0:114` | 0.00132116 probability density | `evidence_5830eda2d88802143396ecee` |
| [447] | `density:0:115` | 0.00107517 probability density | `evidence_58cf579c0bb898ee3794a5a8` |
| [448] | `density:0:116` | 0.000858069 probability density | `evidence_eee9ec6adf3ba887cfb199d9` |
| [449] | `density:0:117` | 0.000732668 probability density | `evidence_83edfeafbd65b48f9a45fa5a` |
| [450] | `density:0:118` | 0.000595387 probability density | `evidence_1480fcba11f8768991c9fb9b` |
| [451] | `density:0:119` | 0.000474227 probability density | `evidence_9a338b76fdae8a16ec092ff9` |
| [452] | `density:0:120` | 0.000386076 probability density | `evidence_ffc07c392a3bb738fb9f7256` |
| [453] | `density:0:121` | 0.000315922 probability density | `evidence_cdad6c8396ba2d7068aa69b9` |
| [454] | `density:0:122` | 0.000250626 probability density | `evidence_c7fcf066ffcb4c40f0f9cec9` |
| [455] | `density:0:123` | 0.000203757 probability density | `evidence_13a3ab3a53d206c56b61aa35` |
| [456] | `density:0:124` | 0.000160477 probability density | `evidence_9085b53063edf2377f93bacc` |
| [457] | `density:0:125` | 0.000128494 probability density | `evidence_e780eb87f4982de5de40528e` |
| [458] | `density:0:126` | 0.000102739 probability density | `evidence_762983c4d64324815f39d12a` |
| [459] | `density:0:127` | 8.20877e-05 probability density | `evidence_6e3e46ad690c152c3c633da2` |
| [460] | `density:0:128` | 6.51888e-05 probability density | `evidence_a230e403d0e5974b280fd3ec` |
| [461] | `density:0:129` | 5.03052e-05 probability density | `evidence_2e25098df78cc018ba42857e` |
| [462] | `density:0:130` | 4.0205e-05 probability density | `evidence_489edeb2016ebecfc20c3438` |
| [463] | `density:0:131` | 3.17751e-05 probability density | `evidence_fbf1f64a8c76c4e6b947589a` |
| [464] | `density:0:132` | 2.6309e-05 probability density | `evidence_46d653d6d86ba5c9e78e3c4b` |
| [465] | `density:0:133` | 2.10086e-05 probability density | `evidence_a33744eadc67df2c4333e2fe` |
| [466] | `density:0:134` | 1.6959e-05 probability density | `evidence_425a1b63566f31da30a27bb3` |
| [467] | `density:0:135` | 1.30315e-05 probability density | `evidence_26d5fef96e69831c26fbecb8` |
| [468] | `density:0:136` | 1.0619e-05 probability density | `evidence_2d5b2d9a04627824902b0087` |
| [469] | `density:0:137` | 8.47254e-06 probability density | `evidence_c7421f0f497aa7e2d7522708` |
| [470] | `density:0:138` | 6.85504e-06 probability density | `evidence_2ad25728c8cd5bbdbf50f161` |
| [471] | `density:0:139` | 5.3472e-06 probability density | `evidence_49e59d1d161520e231d6c074` |
| [472] | `density:0:140` | 4.38608e-06 probability density | `evidence_68b055a82808b44f6af6c854` |
| [473] | `density:0:141` | 3.50848e-06 probability density | `evidence_3bd1a5a5c2091af07bc3c2e7` |
| [474] | `density:0:142` | 2.86474e-06 probability density | `evidence_947bad535a935cb23151e2fd` |
| [475] | `density:0:143` | 2.39971e-06 probability density | `evidence_c9885d768941ec11ee7034b2` |
| [476] | `density:0:144` | 1.95035e-06 probability density | `evidence_d4e9d0b525c232476eac9fe5` |
| [477] | `density:0:145` | 1.59348e-06 probability density | `evidence_8e2c6cda436ed5ee74401d51` |
| [478] | `density:0:146` | 1.2968e-06 probability density | `evidence_451212c064a4516f1f3ce482` |
| [479] | `density:0:147` | 1.04793e-06 probability density | `evidence_40a0f065aac8f9e59f9fe3a5` |
| [480] | `density:0:148` | 8.48027e-07 probability density | `evidence_45d4efa6fd7b84e8da455f21` |
| [481] | `density:0:149` | 7.07598e-07 probability density | `evidence_26a924f21444f58273b0f866` |
| [482] | `density:0:150` | 5.95264e-07 probability density | `evidence_690563cff2fab7006c901c97` |
| [483] | `density:0:151` | 5.09891e-07 probability density | `evidence_dce7368d85f5029fb7c56eab` |
| [484] | `density:0:152` | 4.24419e-07 probability density | `evidence_aff6c5d00e8bae457eac63ea` |
| [485] | `density:0:153` | 3.60404e-07 probability density | `evidence_68b36bf71c185ae3f48929f9` |
| [486] | `density:0:154` | 3.24407e-07 probability density | `evidence_112045b638afa36469d1ee28` |
| [487] | `density:0:155` | 2.77257e-07 probability density | `evidence_57dca23cc89032f7b4718a5e` |
| [488] | `density:0:156` | 2.53589e-07 probability density | `evidence_7d3e349f528816514b2682b6` |
| [489] | `density:0:157` | 2.22741e-07 probability density | `evidence_daac3077fced9242fea26fe8` |
| [490] | `density:0:158` | 1.83481e-07 probability density | `evidence_ef32b17bb8a518bba531f14e` |
| [491] | `density:0:159` | 1.68803e-07 probability density | `evidence_c7aac4f1953eb63a86f277ed` |
| [492] | `density:1:0` | 1.72668e-06 probability density | `evidence_7f7d31aab807b7b8a8d89d86` |
| [493] | `density:1:1` | 1.90553e-06 probability density | `evidence_427363ccad98d5a5f22277cd` |
| [494] | `density:1:2` | 2.11599e-06 probability density | `evidence_5d5004c5c3e5c02bf42cebee` |
| [495] | `density:1:3` | 2.34112e-06 probability density | `evidence_85e4f1a29d95d4699a1fe191` |
| [496] | `density:1:4` | 2.60081e-06 probability density | `evidence_5100270fc5552fc51296fe1d` |
| [497] | `density:1:5` | 2.87736e-06 probability density | `evidence_886cf65b618904ec97ea90f6` |
| [498] | `density:1:6` | 3.20239e-06 probability density | `evidence_96cf21b698f1fc3ff7bef389` |
| [499] | `density:1:7` | 3.49946e-06 probability density | `evidence_a60ce4a26641d149e71e2ed4` |
| [500] | `density:1:8` | 3.97393e-06 probability density | `evidence_350c5a6c0810d10920eadde1` |
| [501] | `density:1:9` | 4.67758e-06 probability density | `evidence_83a6e80753d4e598d4b1b07a` |
| [502] | `density:1:10` | 5.45055e-06 probability density | `evidence_1d0449b8799d2c7727d1c7c6` |
| [503] | `density:1:11` | 6.106e-06 probability density | `evidence_904b565d016e70b8c12a3907` |
| [504] | `density:1:12` | 7.32303e-06 probability density | `evidence_bacc19de730b49c9d76f14a7` |
| [505] | `density:1:13` | 8.70305e-06 probability density | `evidence_c8baa3b85e2444a223beed51` |
| [506] | `density:1:14` | 1.04694e-05 probability density | `evidence_51fa4d7d546b3bd54bd9cd2c` |
| [507] | `density:1:15` | 1.21515e-05 probability density | `evidence_efad73b848396bb87abc50a8` |
| [508] | `density:1:16` | 1.44748e-05 probability density | `evidence_08658e732613306163d2e19c` |
| [509] | `density:1:17` | 1.77923e-05 probability density | `evidence_0cae172021dd1a0910934ff4` |
| [510] | `density:1:18` | 2.03439e-05 probability density | `evidence_7dec07c8b32544807e9da1b6` |
| [511] | `density:1:19` | 2.36129e-05 probability density | `evidence_7e0fedd9ea80f705555fd3f8` |
| [512] | `density:1:20` | 2.89973e-05 probability density | `evidence_36302b7d990c78c9dcb64a2d` |
| [513] | `density:1:21` | 3.52421e-05 probability density | `evidence_d6a89bbcb9eef6a24dcf65ef` |
| [514] | `density:1:22` | 4.0469e-05 probability density | `evidence_2796c27159fff3c4e1724010` |
| [515] | `density:1:23` | 5.01593e-05 probability density | `evidence_40e8fea28c39cbd1cf2add4d` |
| [516] | `density:1:24` | 5.87747e-05 probability density | `evidence_9f93e7253b3bf7f23e030ab7` |
| [517] | `density:1:25` | 7.10315e-05 probability density | `evidence_1e407b793b16c19cf9b1ed96` |
| [518] | `density:1:26` | 8.27253e-05 probability density | `evidence_c570362c3935f2ecb5cf91d1` |
| [519] | `density:1:27` | 9.80053e-05 probability density | `evidence_d6e777ed7b468af345f613a6` |
| [520] | `density:1:28` | 0.000117648 probability density | `evidence_68d03c96e6c0124c275233e5` |
| [521] | `density:1:29` | 0.00013677 probability density | `evidence_44ea36679e2e28fb6c628c8a` |
| [522] | `density:1:30` | 0.000162213 probability density | `evidence_aa90fb729779d1d98cd101d4` |
| [523] | `density:1:31` | 0.000194528 probability density | `evidence_a5cc0dc72addae57ebc8aa36` |
| [524] | `density:1:32` | 0.000218644 probability density | `evidence_adfacffc22fc1267945f37a5` |
| [525] | `density:1:33` | 0.000264636 probability density | `evidence_9960b8c7be2a834dc6b53db6` |
| [526] | `density:1:34` | 0.000306316 probability density | `evidence_0fb3cf1ece89e9daac1b46b9` |
| [527] | `density:1:35` | 0.000363353 probability density | `evidence_b83c2cdec3dea8273e9d51f7` |
| [528] | `density:1:36` | 0.000421729 probability density | `evidence_43bf8cb407fac246644d1ab3` |
| [529] | `density:1:37` | 0.000485741 probability density | `evidence_e295b645d5bf97cd51807883` |
| [530] | `density:1:38` | 0.000562103 probability density | `evidence_91afb9781d13d3e74bddb658` |
| [531] | `density:1:39` | 0.000644813 probability density | `evidence_e1b7d421b7e22958c90e3dbf` |
| [532] | `density:1:40` | 0.000738262 probability density | `evidence_b5a550426a2492797ed14971` |
| [533] | `density:1:41` | 0.000828986 probability density | `evidence_a73d50ab80ed04dbbfef0baf` |
| [534] | `density:1:42` | 0.000965133 probability density | `evidence_68ca23fa740b7f7346aead3a` |
| [535] | `density:1:43` | 0.00108552 probability density | `evidence_9a416c81acc78eaa8cc4da23` |
| [536] | `density:1:44` | 0.0011658 probability density | `evidence_4f8cb498a74d15e8447f5470` |
| [537] | `density:1:45` | 0.00135185 probability density | `evidence_ad3865d047abc367a53424b5` |
| [538] | `density:1:46` | 0.00154111 probability density | `evidence_0a4be259568a2558fb281cc8` |
| [539] | `density:1:47` | 0.00172883 probability density | `evidence_ae9f742adef67fd81a71db5f` |
| [540] | `density:1:48` | 0.0019735 probability density | `evidence_085892cc7e06c1edad8a85a2` |
| [541] | `density:1:49` | 0.00217874 probability density | `evidence_ff13b02b91717cc6e35bf1f0` |
| [542] | `density:1:50` | 0.00248575 probability density | `evidence_ce192205d001462f82161155` |
| [543] | `density:1:51` | 0.00264903 probability density | `evidence_baa62a1ab72034d671535df7` |
| [544] | `density:1:52` | 0.00309127 probability density | `evidence_196eba7dac1df18749bc142f` |
| [545] | `density:1:53` | 0.00344279 probability density | `evidence_1cb2d56d98d94063eb6694e6` |
| [546] | `density:1:54` | 0.00405612 probability density | `evidence_c839c64d10da8f23a3334527` |
| [547] | `density:1:55` | 0.00481271 probability density | `evidence_c946658a116c2b25748c8453` |
| [548] | `density:1:56` | 0.00526666 probability density | `evidence_45b57863b6f239cb1b4225c6` |
| [549] | `density:1:57` | 0.00600696 probability density | `evidence_390e66350cdbfac1d29b1cde` |
| [550] | `density:1:58` | 0.0067032 probability density | `evidence_85853c32fa49fafbb281b393` |
| [551] | `density:1:59` | 0.00771898 probability density | `evidence_957e8ebacf970f32fd39ce5b` |
| [552] | `density:1:60` | 0.0086009 probability density | `evidence_bc9d5ddeafd986682efa9b9b` |
| [553] | `density:1:61` | 0.00930543 probability density | `evidence_a93bbdb3c6b29b7faa245bb0` |
| [554] | `density:1:62` | 0.0103104 probability density | `evidence_ea961c9fcc789f1e8e8d144b` |
| [555] | `density:1:63` | 0.0115551 probability density | `evidence_8958acea174881b72aff063b` |
| [556] | `density:1:64` | 0.0128553 probability density | `evidence_7ca4852c1bed9096516adbe1` |
| [557] | `density:1:65` | 0.0142964 probability density | `evidence_4e28ed484e4b7440906764dd` |
| [558] | `density:1:66` | 0.0158737 probability density | `evidence_296459a593ea21a0c182e7d4` |
| [559] | `density:1:67` | 0.0174102 probability density | `evidence_f17d8e4e067093f37f21e0ce` |
| [560] | `density:1:68` | 0.0187033 probability density | `evidence_39e2e3e7a470f507656549f4` |
| [561] | `density:1:69` | 0.0196186 probability density | `evidence_e532ad8ced09b762d0ad09fe` |
| [562] | `density:1:70` | 0.0210019 probability density | `evidence_8cb82b2ddb93c66d93365bbd` |
| [563] | `density:1:71` | 0.0230537 probability density | `evidence_7ff949641fac044abec41284` |
| [564] | `density:1:72` | 0.0247621 probability density | `evidence_d87a0848a90907b18cb3fd5b` |
| [565] | `density:1:73` | 0.0258144 probability density | `evidence_de405f0455e0f3905aa67413` |
| [566] | `density:1:74` | 0.0265497 probability density | `evidence_b49b5cc2c06584255271c263` |
| [567] | `density:1:75` | 0.0278724 probability density | `evidence_3caf053cfa0d2a83b41cd9ab` |
| [568] | `density:1:76` | 0.0283346 probability density | `evidence_7cd7420571bf4b015769bc8b` |
| [569] | `density:1:77` | 0.0281967 probability density | `evidence_f4fdbfd6d5f36a9ae0bbc085` |
| [570] | `density:1:78` | 0.028004 probability density | `evidence_ab9e1ca1ed98e37bc3ba57a0` |
| [571] | `density:1:79` | 0.0272106 probability density | `evidence_fc693f3810485fa7cbfe7847` |
| [572] | `density:1:80` | 0.0265164 probability density | `evidence_f333801ae82a6419ef2f4d7e` |
| [573] | `density:1:81` | 0.0256 probability density | `evidence_212fe3a1c7c42b699c70f509` |
| [574] | `density:1:82` | 0.0240082 probability density | `evidence_1f531856a91c1ab43fc2f3d5` |
| [575] | `density:1:83` | 0.0223236 probability density | `evidence_14efaf1521bca95a76196e9d` |
| [576] | `density:1:84` | 0.0205764 probability density | `evidence_0afc428aed3af05736b546bc` |
| [577] | `density:1:85` | 0.0192349 probability density | `evidence_f28d3bbc77215e73ef2375d6` |
| [578] | `density:1:86` | 0.017467 probability density | `evidence_6b984bac757a952f614d9e26` |
| [579] | `density:1:87` | 0.0156302 probability density | `evidence_7bfbcf4f7dc4c98dd790d7f1` |
| [580] | `density:1:88` | 0.0137596 probability density | `evidence_a5316098d18de26b487f400a` |
| [581] | `density:1:89` | 0.0119704 probability density | `evidence_8a394dc660283c45fcb7193b` |
| [582] | `density:1:90` | 0.010551 probability density | `evidence_0e2a5f43ecce20dd54372767` |
| [583] | `density:1:91` | 0.00901429 probability density | `evidence_714202128a429fa3eb592c0b` |
| [584] | `density:1:92` | 0.0076985 probability density | `evidence_a4d3915e8d45d114cefb37ae` |
| [585] | `density:1:93` | 0.00632096 probability density | `evidence_ecf8c79bb1b29c149a4eb018` |
| [586] | `density:1:94` | 0.00529207 probability density | `evidence_53ca8b0abfbbd5e24a0fe0c3` |
| [587] | `density:1:95` | 0.00438752 probability density | `evidence_4acf33bed7fe2dd8c4bf8c6d` |
| [588] | `density:1:96` | 0.00359276 probability density | `evidence_69cd8a5fe525c26cc0324f56` |
| [589] | `density:1:97` | 0.00287992 probability density | `evidence_7d087b30ccfe652570519464` |
| [590] | `density:1:98` | 0.00228746 probability density | `evidence_b4be044d308526a2bb555a62` |
| [591] | `density:1:99` | 0.00181514 probability density | `evidence_dc2f57c67399c7f7996ac78d` |
| [592] | `density:1:100` | 0.00144287 probability density | `evidence_17559eaa0b71643f7cabed6f` |
| [593] | `density:1:101` | 0.00118605 probability density | `evidence_2adc84af400c7b553a8211bc` |
| [594] | `density:1:102` | 0.000938368 probability density | `evidence_a5335f4c6ad02f4d44a9bee7` |
| [595] | `density:1:103` | 0.000734794 probability density | `evidence_27e03127d00148895da887a0` |
| [596] | `density:1:104` | 0.000601232 probability density | `evidence_52a301b9bbfa3a9335ca60cf` |
| [597] | `density:1:105` | 0.000491486 probability density | `evidence_00c1982ee8ae6efb05e9b9c5` |
| [598] | `density:1:106` | 0.000390122 probability density | `evidence_bc91f9e241520cb4658fad98` |
| [599] | `density:1:107` | 0.00030513 probability density | `evidence_3e5b452eac4b61e2715bfef8` |
| [600] | `density:1:108` | 0.000237971 probability density | `evidence_b42d0a72cbc39833f4a03336` |
| [601] | `density:1:109` | 0.000191348 probability density | `evidence_a346bde785082d584a99c1c8` |
| [602] | `density:1:110` | 0.000147364 probability density | `evidence_24e603a9f6963baa57d3ea0b` |
| [603] | `density:1:111` | 0.000115381 probability density | `evidence_38ea64100ba0260b4d78db58` |
| [604] | `density:1:112` | 9.4719e-05 probability density | `evidence_78a1c5c6d20c4b3cd45eafe1` |
| [605] | `density:1:113` | 7.3506e-05 probability density | `evidence_1621ed1967e6fec369d5d74d` |
| [606] | `density:1:114` | 5.94881e-05 probability density | `evidence_4b66012b35e07246134068a9` |
| [607] | `density:1:115` | 4.90656e-05 probability density | `evidence_439344cb30d23aa9585d208b` |
| [608] | `density:1:116` | 4.11439e-05 probability density | `evidence_82d4bd187b60b15e292b69e1` |
| [609] | `density:1:117` | 3.36825e-05 probability density | `evidence_a3dc34b949f38985a28bd01f` |
| [610] | `density:1:118` | 2.82929e-05 probability density | `evidence_de33b1cf99e2567cad219606` |
| [611] | `density:1:119` | 2.2832e-05 probability density | `evidence_888b13d6a65409d92e740636` |
| [612] | `density:1:120` | 1.87169e-05 probability density | `evidence_d0cb88c8cc358c2ae6a7592a` |
| [613] | `density:1:121` | 1.55239e-05 probability density | `evidence_81655360cbe8429f52002f05` |
| [614] | `density:1:122` | 1.23843e-05 probability density | `evidence_c0c9afd27338b6ff1611d5aa` |
| [615] | `density:1:123` | 1.02644e-05 probability density | `evidence_827a0ee7a2dcef0878e62c5c` |
| [616] | `density:1:124` | 8.1765e-06 probability density | `evidence_cfb5a79040b470d6fb49215e` |
| [617] | `density:1:125` | 6.58337e-06 probability density | `evidence_c4cc938c00b39164c9fed8d6` |
| [618] | `density:1:126` | 5.24891e-06 probability density | `evidence_8a9ce6eae04e7b12f032067d` |
| [619] | `density:1:127` | 4.38374e-06 probability density | `evidence_034f2487182c2c59cff0e9be` |
| [620] | `density:1:128` | 3.7104e-06 probability density | `evidence_4d15882f27d410d136eacbd2` |
| [621] | `density:1:129` | 3.08981e-06 probability density | `evidence_ce1cee89885fc5b09c4e3630` |
| [622] | `density:1:130` | 2.58645e-06 probability density | `evidence_5378e5f3238036141b65a15d` |
| [623] | `density:1:131` | 2.18399e-06 probability density | `evidence_50f0efba2d8ec204c6d45e7e` |
| [624] | `density:1:132` | 1.86821e-06 probability density | `evidence_aca09da12529d9f45bdcffaa` |
| [625] | `density:1:133` | 1.57554e-06 probability density | `evidence_a85724a980e6b1122ea43559` |
| [626] | `density:1:134` | 1.30417e-06 probability density | `evidence_0bae25d8db20345aca3cc946` |
| [627] | `density:1:135` | 1.0636e-06 probability density | `evidence_67f8df1a35f2a07f4e9f2f6a` |
| [628] | `density:1:136` | 8.94595e-07 probability density | `evidence_831a7130683f72aad316f0c7` |
| [629] | `density:1:137` | 7.39836e-07 probability density | `evidence_4d02a99c997c1f7e8ce2ca8c` |
| [630] | `density:1:138` | 6.20739e-07 probability density | `evidence_0f8f54417f28c77dff27a04c` |
| [631] | `density:1:139` | 5.10182e-07 probability density | `evidence_817b942f2ffd42ac42f1b6d3` |
| [632] | `density:1:140` | 4.30713e-07 probability density | `evidence_a7f1a9933e13ec25b401178c` |
| [633] | `density:1:141` | 3.83583e-07 probability density | `evidence_7ad4fb281dd341825fc33a54` |
| [634] | `density:1:142` | 3.46669e-07 probability density | `evidence_b67d99062d2270be75f17b95` |
| [635] | `density:1:143` | 2.98934e-07 probability density | `evidence_3d3837d883e731f1124d0370` |
| [636] | `density:1:144` | 2.56334e-07 probability density | `evidence_35d39981c8052f36ab2e90bf` |
| [637] | `density:1:145` | 2.25661e-07 probability density | `evidence_c97bf005031bd302102f0d74` |
| [638] | `density:1:146` | 1.88696e-07 probability density | `evidence_f823c39c133e841a75db86db` |
| [639] | `density:1:147` | 1.62266e-07 probability density | `evidence_d4a060d356828df73058d472` |
| [640] | `density:1:148` | 1.34108e-07 probability density | `evidence_eeb7f3fe478f1fb8dac343ce` |
| [641] | `density:1:149` | 1.23222e-07 probability density | `evidence_cbfee4956859cd5408952b63` |
| [642] | `density:1:150` | 1.00532e-07 probability density | `evidence_fbce0daf04c74569517b8edc` |
| [643] | `density:1:151` | 8.73438e-08 probability density | `evidence_8e50ea3a637ad2e6f8def06b` |
| [644] | `density:1:152` | 8.44803e-08 probability density | `evidence_542537b943cb1cd2787906d6` |
| [645] | `density:1:153` | 6.80162e-08 probability density | `evidence_2068c8bdc4c9de77045c620b` |
| [646] | `density:1:154` | 6.58335e-08 probability density | `evidence_af1328cd7d200e8ec8e5f0b4` |
| [647] | `density:1:155` | 5.47468e-08 probability density | `evidence_ec09ca28fc321ab67ffced9d` |
| [648] | `density:1:156` | 5.56714e-08 probability density | `evidence_026e0d3dc65f7a24fc9899d5` |
| [649] | `density:1:157` | 4.47372e-08 probability density | `evidence_11a7e8da5dd91ba8fc9f0f51` |
| [650] | `density:1:158` | 4.02178e-08 probability density | `evidence_aebfa9ec2a1318586ef1d76e` |
| [651] | `density:1:159` | 3.88316e-08 probability density | `evidence_9b7a4247f5d870c38dc6d7b9` |

### Warning codes

- `DEVELOPMENT_TABPFN_NOT_RELEASE_ELIGIBLE`
- `DISTRIBUTIONAL_POINT_ESTIMATES`
- `POOLED_STATE_YEAR_LIMITATIONS`

</details>

<div class="distribution-warnings" style="font-size:0.875em;line-height:1.5"><small style="font-size:inherit"><strong>Warnings and interpretation limits</strong><ul><li>This TabPFN-backed managed/local run is development-only, not a hash-locked Track T result, and is ineligible for release claims.</li><li>Point estimates only, without confidence intervals or significance. Quantile changes are distributional, not individual effects. CDFs cover only the evaluated outcome grid; no extrapolation.</li><li>Real-data exploratory state-year aggregates with equal observation weights, repeated states, and omitted income and state/year effects. Within-state dependence and omitted confounding are not addressed. Instrument exclusion and exogeneity remain assumptions.</li><li>One continuous treatment, one continuous outcome, one scalar instrument, and no baseline covariates W.</li><li>Relevance, exclusion, instrument exogeneity, scalar monotonicity, and common support are assumptions; empirical diagnostics do not prove them.</li><li>Local TabPFN v2 uses the recorded checkpoint artifact, but the current runtime image is not release-locked and cannot enter locked Track T evidence.</li><li>These are empirical diagnostics. They do not prove instrument validity or identification.</li><li>The PDF is an approximate density from finite-differencing the displayed CDF grid; it is not separately fitted or smoothed. No tail extrapolation is performed.</li><li>Development-only local TabPFN v2 output. The model artifact identity is recorded, but the ZeroGPU runtime is not release-locked. This run is not eligible for locked Track T evaluation and must not support a release claim.</li></ul></small></div>
