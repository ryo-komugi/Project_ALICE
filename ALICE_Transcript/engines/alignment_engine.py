from core.utils import overlap
import config
import re


class AlignmentEngine:
    """WhisperのWord TimestampとPyannoteのDiarization Segmentsを高精度に統合するエンジン"""

    STANDALONE_BACKCHANNELS = {"はい", "うん", "ええ", "そう", "いや", "えっ", "ああ", "あー", "うーん"}
    SENTENCE_FINAL_TOKENS = {"ね", "よ", "な", "わ", "ぞ", "ぜ", "か", "さ", "ます", "です", "た", "だ", "る", "い", "ない", "ん", "けど", "から", "ので", "はい", "うん"}
    HALLUCINATION_TEXT_RE = re.compile(
        r"^(?:BGM|ＢＧＭ|音楽|拍手|字幕|ご視聴ありがとうございました[。！!]?|チャンネル登録.*|この動画の内容は.*|私は、?私の人生を変えることを知っています.*)$",
        re.IGNORECASE,
    )

    def extract_words(self, whisper_segments, pyannote_segments: list | None = None) -> list:
        """Whisperセグメントから有効な単語（Word）リストを抽出する。
        - 低対数確率や無音区間のハルシネーションセグメントを除外
        - 同一セグメント内の不自然な時間ジャンプ（語頭サブワード取り残し）を補正
        """
        all_words = []
        for seg in whisper_segments or []:
            if seg.words is None:
                continue
            seg_text = (getattr(seg, "text", "") or "").strip()
            no_sp = getattr(seg, "no_speech_prob", 0.0) or 0.0
            avg_lp = getattr(seg, "avg_logprob", 0.0) or 0.0

            # 明らかな低確信度ハルシネーションの除外
            if avg_lp < -1.05:
                continue
            if self.HALLUCINATION_TEXT_RE.match(seg_text) and (no_sp > 0.35 or avg_lp < -0.80):
                continue

            # Pyannote話者区間が提供されている場合、誰の発話とも全く重ならず確信度が低い無音幻覚を除外
            if pyannote_segments and no_sp > 0.60 and avg_lp < -0.80:
                s_start = float(getattr(seg, "start", 0.0) or 0.0)
                s_end = float(getattr(seg, "end", 0.0) or 0.0)
                py_ov = sum(overlap(s_start, s_end, p["start"], p["end"]) for p in pyannote_segments)
                if py_ov < 0.1:
                    continue

            seg_words = []
            for w in seg.words:
                if w.start is None or w.end is None:
                    continue
                text = w.word.strip()
                if not text:
                    continue
                seg_words.append({
                    "start": float(w.start),
                    "end": float(w.end),
                    "text": text
                })

            # 同一Whisperセグメント内で語頭サブワードが長距離ギャップの前に取り残されている場合、後続単語の直前へ引き寄せる
            for k in range(len(seg_words) - 1):
                cur_w = seg_words[k]
                nxt_w = seg_words[k + 1]
                gap = nxt_w["start"] - cur_w["end"]
                cur_txt = cur_w["text"].rstrip()
                has_punct = cur_txt.endswith(("。", "、", "？", "！", "?", "!", ","))
                if (
                    gap > 2.0
                    and len(cur_txt) <= 2
                    and not has_punct
                    and cur_txt not in self.SENTENCE_FINAL_TOKENS
                ):
                    dur = min(0.4, max(0.1, cur_w["end"] - cur_w["start"]))
                    cur_w["end"] = nxt_w["start"]
                    cur_w["start"] = max(0.0, cur_w["end"] - dur)

            all_words.extend(seg_words)
        return all_words

    def assign_speakers(self, words: list, pyannote_segments: list, tolerance_margin: float | None = None) -> list:
        """単語の時間範囲と話者区間を照合し、最適な話者を割り当てる。
        微小な時間軸ズレに対しては tolerance_margin による近傍吸着を行う。
        """
        if not words:
            return []

        if tolerance_margin is None:
            tolerance_margin = getattr(config, "TOLERANCE_MARGIN", 0.35)

        if not pyannote_segments:
            return [
                {
                    "start": w["start"],
                    "end": w["end"],
                    "speaker": "UNKNOWN",
                    "text": w["text"]
                }
                for w in words
            ]

        sorted_segs = sorted(pyannote_segments, key=lambda s: s["start"])
        word_results = []

        for w in words:
            w_start = w["start"]
            w_end = w["end"]
            word_len = max(0.0, w_end - w_start)

            best_speaker = "UNKNOWN"
            best_overlap = 0.0

            # Step 1: 厳密な時間重複（Overlap）の最大値を探索
            for p in sorted_segs:
                ov = overlap(w_start, w_end, p["start"], p["end"])
                if ov > best_overlap:
                    best_overlap = ov
                    best_speaker = p["speaker"]

            # 単語の半分以上がカバーされていれば採用
            if best_overlap >= word_len * 0.5 and word_len > 0:
                pass
            # Step 2: カバー率が不十分な場合、tolerance_margin 内で最も近接する話者を探す
            elif best_speaker == "UNKNOWN" or best_overlap < word_len * 0.3:
                min_dist = float("inf")
                nearest_speaker = best_speaker

                for p in sorted_segs:
                    if w_end <= p["start"]:
                        dist = p["start"] - w_end
                    elif w_start >= p["end"]:
                        dist = w_start - p["end"]
                    else:
                        dist = 0.0

                    if dist < min_dist:
                        min_dist = dist
                        nearest_speaker = p["speaker"]

                if min_dist <= tolerance_margin:
                    best_speaker = nearest_speaker

            word_results.append({
                "start": w_start,
                "end": w_end,
                "speaker": best_speaker,
                "text": w["text"]
            })

        return word_results

    def interpolate_unknown(self, word_results: list, max_gap: float | None = None) -> list:
        """未特定（UNKNOWN）の単語を前後の文脈や時間間隔に基づいて補間し、
        短時間の孤立した話者フリップノイズを平滑化する。
        """
        if not word_results:
            return []

        if max_gap is None:
            max_gap = getattr(config, "INTERPOLATE_MAX_GAP", 1.5)

        micro_flip_max_dur = getattr(config, "MICRO_FLIP_MAX_DURATION", 0.8)

        n = len(word_results)
        results = [dict(w) for w in word_results]

        # Phase 1: サンドイッチ補間（同一話者に挟まれたUNKNOWN区間の補間）
        i = 0
        while i < n:
            if results[i]["speaker"] == "UNKNOWN":
                start_idx = i
                while i < n and results[i]["speaker"] == "UNKNOWN":
                    i += 1
                end_idx = i - 1

                left_spk = results[start_idx - 1]["speaker"] if start_idx > 0 else None
                right_spk = results[end_idx + 1]["speaker"] if end_idx < n - 1 else None

                # 両側が同一話者の場合
                if left_spk and right_spk and left_spk != "UNKNOWN" and left_spk == right_spk:
                    gap = results[end_idx + 1]["start"] - results[start_idx - 1]["end"]
                    if gap <= max_gap * (end_idx - start_idx + 1) or gap <= 3.0:
                        for k in range(start_idx, end_idx + 1):
                            results[k]["speaker"] = left_spk

                # 先頭のUNKNOWN（直後の話者に近接していれば補間）
                elif not left_spk and right_spk and right_spk != "UNKNOWN":
                    gap = results[end_idx + 1]["start"] - results[end_idx]["end"]
                    if gap <= 0.8:
                        for k in range(start_idx, end_idx + 1):
                            results[k]["speaker"] = right_spk

                # 末尾のUNKNOWN（直前の話者に近接していれば補間）
                elif left_spk and left_spk != "UNKNOWN" and not right_spk:
                    gap = results[start_idx]["start"] - results[start_idx - 1]["end"]
                    if gap <= 0.8:
                        for k in range(start_idx, end_idx + 1):
                            results[k]["speaker"] = left_spk

                # 異なる話者に挟まれている場合（近接距離に応じて割り当て、0.8秒まで許容）
                elif left_spk and right_spk and left_spk != "UNKNOWN" and right_spk != "UNKNOWN":
                    for k in range(start_idx, end_idx + 1):
                        dist_left = results[k]["start"] - results[start_idx - 1]["end"]
                        dist_right = results[end_idx + 1]["start"] - results[k]["end"]
                        if dist_left < dist_right and dist_left <= 0.8:
                            results[k]["speaker"] = left_spk
                        elif dist_right <= dist_left and dist_right <= 0.8:
                            results[k]["speaker"] = right_spk
            else:
                i += 1

        # Phase 2: 単発の孤立話者ノイズ（0.25秒以下の1トークンフリップ）の平滑化
        for k in range(1, n - 1):
            prev_spk = results[k - 1]["speaker"]
            next_spk = results[k + 1]["speaker"]
            cur_spk = results[k]["speaker"]

            if prev_spk != "UNKNOWN" and prev_spk == next_spk and cur_spk != prev_spk:
                token_dur = results[k]["end"] - results[k]["start"]
                span_gap = results[k + 1]["start"] - results[k - 1]["end"]
                if token_dur <= 0.25 and span_gap <= 1.2:
                    results[k]["speaker"] = prev_spk

        # Phase 3: マイクロフリップ平滑化（同一話者に挟まれた0.8秒以下の単発・短時間異話者トークンを除去）
        m = 1
        while m < n - 1:
            prev_spk = results[m - 1]["speaker"]
            cur_spk = results[m]["speaker"]
            if prev_spk != "UNKNOWN" and cur_spk != prev_spk:
                j = m
                while j < n and results[j]["speaker"] == cur_spk:
                    j += 1
                if j < n:
                    next_spk = results[j]["speaker"]
                    if next_spk == prev_spk:
                        dur = results[j - 1]["end"] - results[m]["start"]
                        gap_before = results[m]["start"] - results[m - 1]["end"]
                        gap_after = results[j]["start"] - results[j - 1]["end"]
                        if dur <= micro_flip_max_dur and gap_before <= 0.6 and gap_after <= 0.6:
                            for k in range(m, j):
                                results[k]["speaker"] = prev_spk
                m = j
            else:
                m += 1

        return results

    @staticmethod
    def _join_words(w1_text: str, w2_text: str) -> str:
        """単語テキストを自然に結合する（英数字間のみ半角スペース挿入、日本語はそのまま結合）"""
        if not w1_text:
            return w2_text
        if not w2_text:
            return w1_text
        if w1_text[-1].isascii() and w1_text[-1].isalnum() and w2_text[0].isascii() and w2_text[0].isalnum():
            return f"{w1_text} {w2_text}"
        return f"{w1_text}{w2_text}"

    def build_utterances(
        self,
        assigned_words: list,
        whisper_segments: list | None = None,
        pause_threshold: float | None = None,
        max_duration: float | None = None
    ) -> list:
        """単語リストから発話（Utterance）単位を構築する。
        - 話者が変わった地点で分割
        - 同一話者でもポーズ閾値や文末記号＋無音で自然に分割
        - 最大継続時間で長大化をガード
        - 助詞・語尾途中や語頭サブワードの極小セグメント保護マージ（後方＆前方）
        """
        if not assigned_words:
            return []

        if pause_threshold is None:
            pause_threshold = getattr(config, "PAUSE_THRESHOLD", 1.0)
        if max_duration is None:
            max_duration = getattr(config, "MAX_UTTERANCE_DURATION", 25.0)

        utterances = []
        current_start = assigned_words[0]["start"]
        current_end = assigned_words[0]["end"]
        current_speaker = assigned_words[0]["speaker"]
        current_text = assigned_words[0]["text"]

        for w in assigned_words[1:]:
            same_speaker = (w["speaker"] == current_speaker)
            gap = max(0.0, w["start"] - current_end)
            duration = w["end"] - current_start

            has_terminal_punct = current_text.rstrip().endswith(("。", "？", "！", "?", "!"))
            split_on_punct = has_terminal_punct and (gap >= 0.4 or duration >= 15.0)

            should_split = (
                (not same_speaker)
                or (gap >= pause_threshold)
                or (duration >= max_duration)
                or split_on_punct
            )

            if should_split:
                if current_text.strip():
                    utterances.append({
                        "start": round(current_start, 2),
                        "end": round(current_end, 2),
                        "speaker": current_speaker,
                        "text": current_text.strip()
                    })
                current_start = w["start"]
                current_end = w["end"]
                current_speaker = w["speaker"]
                current_text = w["text"]
            else:
                current_text = self._join_words(current_text, w["text"])
                current_end = max(current_end, w["end"])

        if current_text.strip():
            utterances.append({
                "start": round(current_start, 2),
                "end": round(current_end, 2),
                "speaker": current_speaker,
                "text": current_text.strip()
            })

        if len(utterances) < 2:
            return utterances

        # ==========================================
        # Post-Processing 1: 後方マージ（直前発話への吸収）
        # ==========================================
        merge_same_gap = getattr(config, "MERGE_SAME_SPEAKER_GAP", 1.2)
        merged = []
        i = 0
        while i < len(utterances):
            u = utterances[i]

            # 1. 直前と同一話者で、直前が文末記号で終わっておらず、かつ近接している場合はマージ
            if merged and merged[-1]["speaker"] == u["speaker"]:
                prev_text = merged[-1]["text"].rstrip()
                has_prev_terminal = prev_text.endswith(("。", "？", "！", "?", "!"))
                inter_gap = u["start"] - merged[-1]["end"]
                merged_dur = u["end"] - merged[-1]["start"]
                if not has_prev_terminal and inter_gap <= merge_same_gap and merged_dur <= max_duration:
                    merged[-1]["end"] = max(merged[-1]["end"], u["end"])
                    merged[-1]["text"] = self._join_words(merged[-1]["text"], u["text"])
                    i += 1
                    continue

            # 2. 助詞・語尾途中の切断救済マージ（または直前が未完結のままUNKNOWNに落ちた継続節の吸収）
            if merged:
                prev_u = merged[-1]
                prev_text = prev_u["text"].rstrip()
                cur_text = u["text"].strip()
                inter_gap = u["start"] - prev_u["end"]
                merged_dur = u["end"] - prev_u["start"]

                has_prev_terminal = prev_text.endswith(("。", "？", "！", "?", "!"))
                cur_is_tiny = len(cur_text) <= 4 or (u["end"] - u["start"] <= 0.5)

                if not has_prev_terminal and cur_is_tiny and inter_gap <= 0.4 and merged_dur <= max_duration:
                    prev_u["end"] = max(prev_u["end"], u["end"])
                    prev_u["text"] = self._join_words(prev_u["text"], u["text"])
                    i += 1
                    continue

                # 直前が単語途中（句読点なし）で直後がUNKNOWNかつ0.6秒以内の場合も継続発話として吸収
                if (
                    not has_prev_terminal
                    and not prev_text.endswith("、")
                    and u["speaker"] == "UNKNOWN"
                    and inter_gap <= 0.6
                    and merged_dur <= max_duration
                ):
                    prev_u["end"] = max(prev_u["end"], u["end"])
                    prev_u["text"] = self._join_words(prev_u["text"], u["text"])
                    i += 1
                    continue

            merged.append(dict(u))
            i += 1

        # ==========================================
        # Post-Processing 2: 前方マージ（孤立した語頭サブワード・UNKNOWNを直後の発話へ結合）
        # ==========================================
        final_utterances = []
        idx = 0
        while idx < len(merged):
            u = merged[idx]
            cur_text = u["text"].strip()
            has_terminal = cur_text.endswith(("。", "？", "！", "?", "!"))
            is_backchannel = cur_text.rstrip("。、！？!?") in self.STANDALONE_BACKCHANNELS

            if (
                idx + 1 < len(merged)
                and not has_terminal
                and (
                    (u["speaker"] == "UNKNOWN" and len(cur_text) <= 4)
                    or (len(cur_text) == 1 and not is_backchannel)
                )
            ):
                nxt_u = merged[idx + 1]
                gap_to_next = nxt_u["start"] - u["end"]
                combined_dur = nxt_u["end"] - u["start"]
                if gap_to_next <= 1.0 and combined_dur <= max_duration:
                    nxt_u = dict(nxt_u)
                    nxt_u["start"] = min(u["start"], nxt_u["start"])
                    nxt_u["text"] = self._join_words(cur_text, nxt_u["text"])
                    merged[idx + 1] = nxt_u
                    idx += 1
                    continue

            final_utterances.append(u)
            idx += 1

        return self.consolidate_minor_speakers(final_utterances)

    def consolidate_minor_speakers(self, utterances: list) -> list:
        """過剰クラスタリング（5話者以上）時に、総発話時間が極小（3秒未満かつ2発話以下）の
        ゴースト話者を時間的に最も近い主要話者へ統合する。
        """
        if not utterances:
            return utterances

        spk_durations = {}
        spk_counts = {}
        total_dur = 0.0
        for u in utterances:
            spk = u["speaker"]
            if spk == "UNKNOWN":
                continue
            dur = max(0.0, u["end"] - u["start"])
            spk_durations[spk] = spk_durations.get(spk, 0.0) + dur
            spk_counts[spk] = spk_counts.get(spk, 0) + 1
            total_dur += dur

        if len(spk_durations) <= 4 or total_dur <= 0:
            return utterances

        minor_speakers = {
            spk for spk, dur in spk_durations.items()
            if spk_counts.get(spk, 0) <= 2 and dur < 3.0 and (dur / total_dur) < 0.01
        }
        if not minor_speakers or len(spk_durations) - len(minor_speakers) < 2:
            return utterances

        major_indices = [
            i for i, u in enumerate(utterances)
            if u["speaker"] != "UNKNOWN" and u["speaker"] not in minor_speakers
        ]
        if not major_indices:
            return utterances

        for i, u in enumerate(utterances):
            if u["speaker"] in minor_speakers:
                best_spk = u["speaker"]
                best_dist = float("inf")
                for m_idx in major_indices:
                    m_u = utterances[m_idx]
                    if m_u["end"] <= u["start"]:
                        dist = u["start"] - m_u["end"]
                    elif m_u["start"] >= u["end"]:
                        dist = m_u["start"] - u["end"]
                    else:
                        dist = 0.0
                    if dist < best_dist:
                        best_dist = dist
                        best_spk = m_u["speaker"]
                u["speaker"] = best_spk

        return utterances

    def align(self, whisper_segments, pyannote_segments):
        """WhisperセグメントとPyannoteセグメントからアライメントを実行する"""
        words = self.extract_words(whisper_segments, pyannote_segments=pyannote_segments)
        assigned = self.assign_speakers(words, pyannote_segments)
        assigned = self.interpolate_unknown(assigned)
        results = self.build_utterances(assigned, whisper_segments=whisper_segments)
        return assigned, results

    def run(self, job):
        """Pipelineから呼び出される実行エントリポイント"""
        job.assigned_words, job.results = self.align(job.whisper_segments, job.pyannote_segments)
