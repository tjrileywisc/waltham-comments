
# Waltham city council meeting diarization and transcription tool

Keep city council honest by adding an extra level of transparency through diarization (identifying who said what) and
transcriptioning of each statement said in session.

Dependencies are managed by the wonderful `uv` tool. Diarization and transcription are handled by `whisperx`.

(may also be a deliberately over-engineered refresher of python scripting for me)

If you're running this yourself, you'll need to get a huggingface token, which should go into a json file (config.json) with the key `HF_TOKEN`.
