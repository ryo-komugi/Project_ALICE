from core.utils import overlap
import config


class AlignmentEngine:
    """WhisperのWord TimestampとPyannoteのDiarization Segmentsを高精度に統合するエンジン"""

    def extract_words(self, whisper_segments) -> list:
        """Whisperセグメントから有効な単語（Word）リストを抽出する"""
        all_words = []
        for seg in whisper_segments or []:
            if seg.words is None:
                continue
            for w in seg.words:
                if w.start is None or w.end is None:
                    continue
                text = w.word.strip()
                if not text:
                    continue
                all_words.append({
                    "start": float(w.start),
                    "end": float(w.end),
                    "text": text
                })
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

        # 開始時間で整序
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
                    if gap <= 0.5:
                        for k in range(start_idx, end_idx + 1):
                            results[k]["speaker"] = right_spk

                # 末尾のUNKNOWN（直前の話者に近接していれば補間）
                elif left_spk and left_spk != "UNKNOWN" and not right_spk:
                    gap = results[start_idx]["start"] - results[start_idx - 1]["end"]
                    if gap <= 0.5:
                        for k in range(start_idx, end_idx + 1):
                            results[k]["speaker"] = left_spk

                # 異なる話者に挟まれている場合（近接距離に応じて割り当て）
                elif left_spk and right_spk and left_spk != "UNKNOWN" and right_spk != "UNKNOWN":
                    for k in range(start_idx, end_idx + 1):
                        dist_left = results[k]["start"] - results[start_idx - 1]["end"]
                        dist_right = results[end_idx + 1]["start"] - results[k]["end"]
                        if dist_left < dist_right and dist_left <= 0.4:
                            results[k]["speaker"] = left_spk
                        elif dist_right <= dist_left and dist_right <= 0.4:
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
        # 例: A A A [B(0.3s)] A A A -> すべて A に統合
        m = 1
        while m < n - 1:
            prev_spk = results[m - 1]["speaker"]
            cur_spk = results[m]["speaker"]
            if prev_spk != "UNKNOWN" and cur_spk != prev_spk:
                # cur_spk の連続区間を測る
                j = m
                while j < n and results[j]["speaker"] == cur_spk:
                    j += 1
                if j < n:
                    next_spk = results[j]["speaker"]
                    if next_spk == prev_spk:
                        dur = results[j - 1]["end"] - results[m]["start"]
                        gap_before = results[m]["start"] - results[m - 1]["end"]
                        gap_after = results[j]["start"] - results[j - 1]["end"]
                        # micro_flip_max_dur以下で、前後の間隔が小さい場合は同一話者の連続発話と判定
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
        - 助詞・文末未完結の極小セグメントの保護マージ
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

            # 文末記号かつ一定のポーズがある場合は文境界と判定
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

        # ==========================================
        # Post-Processing: 発話細片化の解消と平滑化マージ
        # ==========================================
        if len(utterances) < 2:
            return utterances

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

            # 2. 助詞・語尾途中の切断救済マージ
            # 直前が文末記号で終わっておらず、かつ現在の発話が極短（4文字以下または0.5秒以下）で近接（0.4秒以下）している場合
            if merged:
                prev_u = merged[-1]
                prev_text = prev_u["text"].rstrip()
                cur_text = u["text"].strip()
                inter_gap = u["start"] - prev_u["end"]

                has_prev_terminal = prev_text.endswith(("。", "？", "！", "?", "!"))
                cur_is_tiny = len(cur_text) <= 4 or (u["end"] - u["start"] <= 0.5)

                if not has_prev_terminal and cur_is_tiny and inter_gap <= 0.4:
                    # 語尾パーツ（「てるの?」「てくれた」「理由?」など）と判断し直前発話へ吸収
                    prev_u["end"] = max(prev_u["end"], u["end"])
                    prev_u["text"] = self._join_words(prev_u["text"], u["text"])
                    i += 1
                    continue

            merged.append(dict(u))
            i += 1

        return merged

    def align(self, whisper_segments, pyannote_segments):
        """WhisperセグメントとPyannoteセグメントからアライメントを実行する"""
        words = self.extract_words(whisper_segments)
        assigned = self.assign_speakers(words, pyannote_segments)
        assigned = self.interpolate_unknown(assigned)
        results = self.build_utterances(assigned, whisper_segments=whisper_segments)
        return assigned, results

    def run(self, job):
        """Pipelineから呼び出される実行エントリポイント"""
        job.assigned_words, job.results = self.align(job.whisper_segments, job.pyannote_segments)
