import json
from config import DEBUG_EXPORT
from core.utils import format_time


class Exporter:
    def create_summary(self, job, model_name) -> str:
        return (
            "\n===== 実行時間 =====\n"
            f"Pipeline全体：{format_time(job.total_time)}\n"
            f"pyannote：{format_time(job.py_time)}\n"
            f"Whisper({model_name})：{format_time(job.wh_time)}\n"
            f"Alignment：{format_time(job.aln_time)}\n"
            f"Normalization：{format_time(job.norm_time)}\n"
        )

    def export_json(self, job):
        with open(job.transcript_json, "w", encoding="utf-8") as jf:
            json.dump(job.results, jf, ensure_ascii=False, indent=2)

    def export_txt(self, job, summary):
        with open(job.output_txt, "w", encoding="utf-8") as f:
            for r in job.results:
                line = (
                    f"[{format_time(r['start'])} "
                    f"- {format_time(r['end'])}] "
                    f"{r['speaker']}: "
                    f"{r['text']}"
                )
                f.write(line + "\n")
            f.write(summary)
    
    def export_metadata(self, job, model_name):
        metadata = {
            "basename": job.basename,
            "timestamp": job.timestamp,
            "status": job.status.value,
            "input_audio": str(job.input_audio),
            "output_txt": str(job.output_txt),
            "transcript_json": str(job.transcript_json),
            "whisper_model": model_name,
            "execution": {
                "total": round(job.total_time, 2),
                "pyannote": round(job.py_time, 2),
                "whisper": round(job.wh_time, 2),
                "alignment": round(job.aln_time, 2),
                "normalization": round(job.norm_time, 2),
            }
        }
        with open(job.metadata_json, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    def export_failure_metadata(self, job, model_name, error_message: str):
        """パイプライン異常終了時にエラー情報を metadata.json に記録する"""
        if not job or not job.metadata_json:
            return
        metadata = {
            "basename": job.basename,
            "timestamp": job.timestamp,
            "status": "FAILED",
            "error": str(error_message),
            "input_audio": str(job.input_audio) if job.input_audio else "",
            "whisper_model": model_name,
            "execution": {
                "total": round(job.total_time, 2),
                "pyannote": round(job.py_time, 2),
                "whisper": round(job.wh_time, 2),
                "alignment": round(job.aln_time, 2),
                "normalization": round(job.norm_time, 2),
            }
        }
        try:
            with open(job.metadata_json, "w", encoding="utf-8") as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ===================================================================================================
    def export_debug(self, job):
        debug_dir = job.transcript_json.parent / "debug"
        debug_dir.mkdir(exist_ok=True)
        self.export_pyannote(job, debug_dir)
        self.export_assigned(job, debug_dir) 
        self.export_whisper(job, debug_dir)
    
    def export_pyannote(self, job, debug_dir):
        with open(debug_dir / "pyannote_segments.json", "w", encoding="utf-8") as f:
            json.dump(job.pyannote_segments, f, ensure_ascii=False, indent=2)
        
    def export_assigned(self, job, debug_dir):
        with open(debug_dir / "assigned_words.json", "w", encoding="utf8") as f:
            json.dump(job.assigned_words, f, ensure_ascii=False, indent=2)
    
    def export_whisper(self, job, debug_dir):
        whisper_segment = [self.whisper_segment_to_dict(seg) for seg in job.whisper_segments]
        with open(debug_dir / "whisper_segments.json", "w", encoding="utf8") as f:
            json.dump(whisper_segment, f, ensure_ascii=False, indent=2)
    
    def whisper_segment_to_dict(self, segment):
        return {
            "start": float(segment.start),
            "end": float(segment.end),
            "text": segment.text,
            "words": [
                {
                    "start": float(word.start),
                    "end": float(word.end),
                    "text": word.word.strip(),
                    "probability": float(word.probability)
                }
                for word in getattr(segment, "words", None) or []
            ]
        }
    # ===================================================================================================

    def run(self, job, model_name):
        summary = self.create_summary(job, model_name)
        self.export_txt(job, summary)
        self.export_json(job)
        self.export_metadata(job, model_name)
        if DEBUG_EXPORT:
            self.export_debug(job)
        print(summary)
        print(f"Saved: {job.output_txt}")
        return summary
