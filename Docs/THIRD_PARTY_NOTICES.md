# Third-Party Notices — Project ALICE

最終更新: 2026-11-20

Project_ALICE が利用しているサードパーティのソフトウェア、AIモデル、フォント、素材と、そのライセンスの一覧です。
各ソフトウェアやモデルの著作権は、それぞれの権利者に帰属します。

> **運用前提:** 社内に限定して提供する（社外への配布や一般公開はしない）。
> この前提が変わる場合（社外への配布、パッケージやDockerイメージでの提供など）は、本書を見直し、各ライセンスの全文を同梱すること。

---

## 1. AI モデル

| 用途 | モデル | ライセンス | 備考 |
|---|---|---|---|
| 文字起こし | OpenAI Whisper large-v3（`Systran/faster-whisper-large-v3`） | MIT | `ALICE_Transcript/config.py` |
| 文字起こし（オプション） | `deepdml/faster-whisper-large-v3-turbo-ct2` | MIT | |
| 話者分離 | `pyannote/speaker-diarization-3.1` | MIT | Hugging Face の gated モデル（利用条件への同意が必要） |
| 話者分離（内部） | `pyannote/segmentation-3.0` | MIT | gated |
| 話者埋め込み（内部） | `pyannote/wespeaker-voxceleb-resnet34-LM` | **CC BY 4.0** | **出典表示が必要**（下記） |
| 議事録・要約 | Gemma 4（`gemma4:12b`, `gemma4:e4b`） | Apache-2.0 | Ollama 経由 |
| 要約（フォールバック） | Qwen3（`qwen3:14b`） | Apache-2.0 | Ollama 経由 |

### CC BY 4.0 の出典表示

```
Speaker embedding model: WeSpeaker ResNet34-LM trained on VoxCeleb,
distributed by pyannote as "pyannote/wespeaker-voxceleb-resnet34-LM".
Used unmodified (未改変で利用).
Licensed under CC BY 4.0 — https://creativecommons.org/licenses/by/4.0/
WeSpeaker: https://github.com/wenet-e2e/wespeaker
```

画面上では、Rabbit-Hole の「About & Licenses」ダイアログにも同じ趣旨の表示をしています。

---

## 2. 推論基盤・ランタイム

| ソフトウェア | ライセンス |
|---|---|
| Ollama | MIT |
| faster-whisper | MIT |
| CTranslate2 | MIT |
| pyannote.audio | MIT |
| PyTorch / torchvision | BSD-3-Clause |
| torchaudio | BSD-2-Clause |
| SpeechBrain | Apache-2.0 |
| PyTorch Lightning | Apache-2.0 |
| ONNX Runtime | MIT |
| FFmpeg（OS コマンドとして利用） | LGPL-2.1+ / GPL（ビルドによる） |
| PyAV | BSD-3-Clause（同梱の FFmpeg は LGPL） |
| NVIDIA CUDA ライブラリ（`nvidia-*-cu12`） | NVIDIA Software License Agreement（独自 EULA） |

---

## 3. サーバー（ALICE_Core / core_env）

主なもの:

| パッケージ | ライセンス |
|---|---|
| FastAPI | MIT |
| Starlette | BSD-3-Clause |
| Uvicorn | BSD-3-Clause |
| Pydantic / pydantic-core | MIT |
| requests | Apache-2.0 |
| aiohttp | Apache-2.0 AND MIT |
| line-bot-sdk | Apache-2.0 |
| python-docx | MIT |
| Markdown | BSD-3-Clause |
| Pillow | MIT-CMU |
| cryptography | Apache-2.0 OR BSD-3-Clause |
| python-multipart | Apache-2.0 |
| python-dotenv | BSD-3-Clause |
| pywebpush / py-vapid | MPL-2.0 |
| certifi | MPL-2.0 |

上記以外の依存パッケージ（anyio, attrs, idna, urllib3, yarl など）も、すべて MIT / BSD / Apache-2.0 / PSF-2.0 / MPL-2.0 のいずれかです。

一覧は、次のコマンドで再生成できます:

```bash
myenv/core_env/bin/python - <<'EOF'
import importlib.metadata as m
for d in sorted(m.distributions(), key=lambda d: d.metadata['Name'].lower()):
    md = d.metadata
    print(md['Name'], d.version, md.get('License-Expression') or md.get('License') or '', sep=' | ')
EOF
```

> **補足:** `edge-tts`（LGPLv3）が core_env に入っていますが、ALICE のコードからは使っていません（CHESHIRE と venv を共用している名残り）。

---

## 4. フロントエンド

| 項目 | 読み込み方 | ライセンス |
|---|---|---|
| marked.js | 同梱（`ALICE_Core/static/admin/marked.min.js`） | MIT — © 2011-2025 Christopher Jeffrey（ファイル先頭の著作権表示を消さないこと） |
| Tailwind CSS | CDN（`cdn.tailwindcss.com`） | MIT |
| Poppins | Google Fonts CDN | SIL OFL 1.1 |
| BIZ UDPGothic | Google Fonts CDN | SIL OFL 1.1 |
| Inter | Google Fonts CDN | SIL OFL 1.1 |
| JetBrains Mono | Google Fonts CDN | SIL OFL 1.1 |

> 本社などの閉域網に展開する前に、フォントと Tailwind をセルフホストに切り替えることを推奨します。
> フォントを同梱する場合は、OFL のライセンス文（`OFL.txt`）も一緒に配置すること。

---

## 5. 外部サービス

| サービス | 用途 | 規約 |
|---|---|---|
| LINE Messaging API | 通知・Bot | LINE ヤフー社の API 利用規約 |
| Hugging Face Hub | モデルのダウンロード（初回のみ） | Hugging Face の利用規約、各モデルの利用条件（gated） |

---

## 6. キャラクター・画像・動画

`ALICE_Navigators/*/images/`、`ALICE_Core/static/admin/` などにある、キャラクター（Noel / Kureha / Stella）、ロゴ、背景、アイコン、アニメーションは、
Project ALICE チームが **生成AI（ChatGPT / Gemini）** を使って制作したオリジナル素材です。第三者の素材は使っていません。

- OpenAI の利用規約上、ChatGPT の出力の権利は利用者に帰属します。
- Google は Gemini の生成物について所有権を主張しません。
- どちらも、クレジット表示の義務はありません。各社の禁止用途ポリシーには従うこと。
- Gemini の画像には SynthID（不可視の透かし）、ChatGPT の画像には C2PA メタデータが含まれる場合があります。どちらも除去しないこと。

---

## 7. 代表的なライセンス条文・参照先

- **MIT License:** https://opensource.org/licenses/MIT
- **BSD 3-Clause License:** https://opensource.org/licenses/BSD-3-Clause
- **Apache License 2.0:** https://www.apache.org/licenses/LICENSE-2.0
- **Creative Commons Attribution 4.0 (CC BY 4.0):** https://creativecommons.org/licenses/by/4.0/legalcode
- **SIL Open Font License 1.1:** https://openfontlicense.org/

以下に、実際に同梱・利用している主要パッケージ（FastAPI / Starlette / Requests）の `.dist-info` から抽出したライセンス全文を記載します。

### 7.1 MIT License（例: FastAPI）

```text
The MIT License (MIT)

Copyright (c) 2018 Sebastián Ramírez

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```

### 7.2 BSD 3-Clause License（例: Starlette）

```text
Copyright © 2018, [Encode OSS Ltd](https://www.encode.io/).
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.

* Neither the name of the copyright holder nor the names of its
  contributors may be used to endorse or promote products derived from
  this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

### 7.3 Apache License 2.0（例: Requests）

```text
Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/

   TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION

   1. Definitions.

      "License" shall mean the terms and conditions for use, reproduction,
      and distribution as defined by Sections 1 through 9 of this document.

      "Licensor" shall mean the copyright owner or entity authorized by
      the copyright owner that is granting the License.

      "Legal Entity" shall mean the union of the acting entity and all
      other entities that control, are controlled by, or are under common
      control with that entity. For the purposes of this definition,
      "control" means (i) the power, direct or indirect, to cause the
      direction or management of such entity, whether by contract or
      otherwise, or (ii) ownership of fifty percent (50%) or more of the
      outstanding shares, or (iii) beneficial ownership of such entity.

      "You" (or "Your") shall mean an individual or Legal Entity
      exercising permissions granted by this License.

      "Source" form shall mean the preferred form for making modifications,
      including but not limited to software source code, documentation
      source, and configuration files.

      "Object" form shall mean any form resulting from mechanical
      transformation or translation of a Source form, including but
      not limited to compiled object code, generated documentation,
      and conversions to other media types.

      "Work" shall mean the work of authorship, whether in Source or
      Object form, made available under the License, as indicated by a
      copyright notice that is included in or attached to the work
      (an example is provided in the Appendix below).

      "Derivative Works" shall mean any work, whether in Source or Object
      form, that is based on (or derived from) the Work and for which the
      editorial revisions, annotations, elaborations, or other modifications
      represent, as a whole, an original work of authorship. For the purposes
      of this License, Derivative Works shall not include works that remain
      separable from, or merely link (or bind by name) to the interfaces of,
      the Work and Derivative Works thereof.

      "Contribution" shall mean any work of authorship, including
      the original version of the Work and any modifications or additions
      to that Work or Derivative Works thereof, that is intentionally
      submitted to Licensor for inclusion in the Work by the copyright owner
      or by an individual or Legal Entity authorized to submit on behalf of
      the copyright owner. For the purposes of this definition, "submitted"
      means any form of electronic, verbal, or written communication sent
      to the Licensor or its representatives, including but not limited to
      communication on electronic mailing lists, source code control systems,
      and issue tracking systems that are managed by, or on behalf of, the
      Licensor for the purpose of discussing and improving the Work, but
      excluding communication that is conspicuously marked or otherwise
      designated in writing by the copyright owner as "Not a Contribution."

      "Contributor" shall mean Licensor and any individual or Legal Entity
      on behalf of whom a Contribution has been received by Licensor and
      subsequently incorporated within the Work.

   2. Grant of Copyright License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      copyright license to reproduce, prepare Derivative Works of,
      publicly display, publicly perform, sublicense, and distribute the
      Work and such Derivative Works in Source or Object form.

   3. Grant of Patent License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      (except as stated in this section) patent license to make, have made,
      use, offer to sell, sell, import, and otherwise transfer the Work,
      where such license applies only to those patent claims licensable
      by such Contributor that are necessarily infringed by their
      Contribution(s) alone or by combination of their Contribution(s)
      with the Work to which such Contribution(s) was submitted. If You
      institute patent litigation against any entity (including a
      cross-claim or counterclaim in a lawsuit) alleging that the Work
      or a Contribution incorporated within the Work constitutes direct
      or contributory patent infringement, then any patent licenses
      granted to You under this License for that Work shall terminate
      as of the date such litigation is filed.

   4. Redistribution. You may reproduce and distribute copies of the
      Work or Derivative Works thereof in any medium, with or without
      modifications, and in Source or Object form, provided that You
      meet the following conditions:

      (a) You must give any other recipients of the Work or
          Derivative Works a copy of this License; and

      (b) You must cause any modified files to carry prominent notices
          stating that You changed the files; and

      (c) You must retain, in the Source form of any Derivative Works
          that You distribute, all copyright, patent, trademark, and
          attribution notices from the Source form of the Work,
          excluding those notices that do not pertain to any part of
          the Derivative Works; and

      (d) If the Work includes a "NOTICE" text file as part of its
          distribution, then any Derivative Works that You distribute must
          include a readable copy of the attribution notices contained
          within such NOTICE file, excluding those notices that do not
          pertain to any part of the Derivative Works, in at least one
          of the following places: within a NOTICE text file distributed
          as part of the Derivative Works; within the Source form or
          documentation, if provided along with the Derivative Works; or,
          within a display generated by the Derivative Works, if and
          wherever such third-party notices normally appear. The contents
          of the NOTICE file are for informational purposes only and
          do not modify the License. You may add Your own attribution
          notices within Derivative Works that You distribute, alongside
          or as an addendum to the NOTICE text from the Work, provided
          that such additional attribution notices cannot be construed
          as modifying the License.

      You may add Your own copyright statement to Your modifications and
      may provide additional or different license terms and conditions
      for use, reproduction, or distribution of Your modifications, or
      for any such Derivative Works as a whole, provided Your use,
      reproduction, and distribution of the Work otherwise complies with
      the conditions stated in this License.

   5. Submission of Contributions. Unless You explicitly state otherwise,
      any Contribution intentionally submitted for inclusion in the Work
      by You to the Licensor shall be under the terms and conditions of
      this License, without any additional terms or conditions.
      Notwithstanding the above, nothing herein shall supersede or modify
      the terms of any separate license agreement you may have executed
      with Licensor regarding such Contributions.

   6. Trademarks. This License does not grant permission to use the trade
      names, trademarks, service marks, or product names of the Licensor,
      except as required for reasonable and customary use in describing the
      origin of the Work and reproducing the content of the NOTICE file.

   7. Disclaimer of Warranty. Unless required by applicable law or
      agreed to in writing, Licensor provides the Work (and each
      Contributor provides its Contributions) on an "AS IS" BASIS,
      WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
      implied, including, without limitation, any warranties or conditions
      of TITLE, NON-INFRINGEMENT, MERCHANTABILITY, or FITNESS FOR A
      PARTICULAR PURPOSE. You are solely responsible for determining the
      appropriateness of using or redistributing the Work and assume any
      risks associated with Your exercise of permissions under this License.

   8. Limitation of Liability. In no event and under no legal theory,
      whether in tort (including negligence), contract, or otherwise,
      unless required by applicable law (such as deliberate and grossly
      negligent acts) or agreed to in writing, shall any Contributor be
      liable to You for damages, including any direct, indirect, special,
      incidental, or consequential damages of any character arising as a
      result of this License or out of the use or inability to use the
      Work (including but not limited to damages for loss of goodwill,
      work stoppage, computer failure or malfunction, or any and all
      other commercial damages or losses), even if such Contributor
      has been advised of the possibility of such damages.

   9. Accepting Warranty or Additional Liability. While redistributing
      the Work or Derivative Works thereof, You may choose to offer,
      and charge a fee for, acceptance of support, warranty, indemnity,
      or other liability obligations and/or rights consistent with this
      License. However, in accepting such obligations, You may act only
      on Your own behalf and on Your sole responsibility, not on behalf
      of any other Contributor, and only if You agree to indemnify,
      defend, and hold each Contributor harmless for any liability
      incurred by, or claims asserted against, such Contributor by reason
      of your accepting any such warranty or additional liability.
```
