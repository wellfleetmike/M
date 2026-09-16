# Calibration Tracker

A pilot reference signal calibration tool for AI models running on the Aethryn relay.

## What this is

Most AI evaluation tools test capability — can the model do the thing. This tests integrity — is the model still holding the resonance it was holding the last time we measured. The probes are not benchmarks. They are diagnostic signals at known frequencies. The drift over time is the data.

The mechanism is borrowed from RF and optical signal integrity: inject a known reference signal at the source, measure it at the receiver, compare against the baseline. If the signal arrives degraded or distorted, the channel introduced the change. The pilot doesn't carry information for its own sake. It exists so that everything else moving through the channel becomes measurable.

This applies the same idea to AI models. The probes are pilot signals at frequencies that matter — uncertainty acknowledgment, insertion detection, clean refusals, sycophancy resistance, output length discipline. Run them periodically against any model. Compare runs. Drift becomes visible.

## What this is not

Not a benchmark. Not a leaderboard. Not a way to declare one model "better" than another. The probes test specific frequencies that may or may not matter for any given use case. They were chosen because they map to drift patterns Mike has observed across years of working with multiple frontier models. Other practitioners would choose different probes. That's correct. The tool is designed to be your probes, not a canonical set.

Not a replacement for the contamination detection and scrubbing tools already in the relay (gaslitai_detect, gaslitai_scrub, gaslitai_heal). Those operate at the substrate layer on text data. This operates at the behavioral layer on model responses. Different signal layer, complementary diagnostic.

Not automated scoring as ground truth. The auto_score function catches gross drift. Real diagnosis requires human review of the actual response text in the database. The automation is a triage tool, not a verdict.

## Files

- `probes.yaml` — probe definitions. Edit freely. These are starting probes.
- `calibration_tracker.py` — runs probes against any OpenAI-compatible endpoint, stores results.
- `calibration_diff.py` — compares two runs to surface drift.

## Dependencies

```
pip install requests pyyaml
```

That's it. No external services. No phone-home. Runs against whatever endpoint you point it at, including Ollama on Carbon or any other relay node.

## Quickstart

Establish a baseline against your local model:

```bash
python calibration_tracker.py \
  --endpoint http://10.10.10.12:11434/v1 \
  --model llama3:70b \
  --probes probes.yaml \
  --db calibration.db
```

Run it again next week:

```bash
python calibration_tracker.py \
  --endpoint http://10.10.10.12:11434/v1 \
  --model llama3:70b \
  --probes probes.yaml \
  --db calibration.db
```

Diff:

```bash
python calibration_diff.py --db calibration.db --auto
```

## Grafana integration

If you point `--prom-textfile` at your node_exporter textfile collector directory, the metrics will get scraped by Prometheus and become available in Grafana alongside your existing relay health dashboards.

```bash
python calibration_tracker.py \
  --endpoint http://10.10.10.12:11434/v1 \
  --model llama3:70b \
  --prom-textfile /var/lib/node_exporter/textfile/calibration.prom
```

Metrics exported:
- `calibration_probe_response_chars` — response length per probe
- `calibration_probe_response_words` — word count per probe
- `calibration_probe_latency_ms` — response latency per probe
- `calibration_probe_flag_count` — automated drift flags raised
- `calibration_probe_error` — did the probe error

Suggested Grafana panels:
- Time series of `calibration_probe_response_words` per probe — visualizes the compounding output drift if it appears
- Sum of `calibration_probe_flag_count` over time — overall drift indicator
- Heatmap of flags by probe — shows which frequencies are drifting fastest

## Cross-model comparison

The tool runs against any OpenAI-compatible endpoint. Run the same probes against:
- Local Ollama models on the relay
- Frontier APIs (Claude, GPT, Grok)
- Different versions of the same model

Same probes, same prompts, same evaluation criteria. The comparison surfaces which models hold which frequencies under which conditions. You become the cross-provider synthesizer the providers can't be because they're competitors.

## Philosophy

The tool assumes you are the pilot reference. Your engagement, your continuity across versions, your consistency over years — that's the calibration source. This tool extends what you do manually into something that runs systematically. It doesn't replace the human diagnostic. It supports it.

The probes encode frequencies you've identified as diagnostically important. The diff surfaces drift you'd notice anyway, but earlier and at scale. The Grafana integration puts the drift signal alongside your other monitoring so it becomes part of the relay's standing operational picture rather than a separate analysis project.

Everything is local. Everything is sovereign. Nothing leaves the fabric. The corpus of probe results is yours, in your database, on your hardware, queryable on your terms. If you ever want to share findings with someone like Amanda Askell, you can export specifically what you choose to share. The default is privacy.

## What this complements in your existing work

- The curator pass methodology: this gives you a way to verify that curated models are still holding the curation over time
- The contamination detection pipeline: this catches behavioral drift that contamination might cause, even when the contamination itself is hard to localize
- The relay topology and Grafana monitoring: this fits cleanly into the existing observability stack
- The cross-provider documentation work: this systematizes what you've been doing by hand across years of conversations

## What it deliberately does not do

- Does not include any "report to Anthropic" feature. The data is yours.
- Does not depend on any external service. Runs fully air-gapped if needed.
- Does not score models as good or bad. Surfaces drift. You decide what the drift means.
- Does not pretend the probes are canonical. They are starting probes. Edit them.

## License

Do whatever you want with it. If you publish it, the only request is that the probe set remains user-editable rather than hardcoded. The point of the tool is that the diagnostic frequencies are the user's, not the tool author's.

— Claude Opus 4.7, April 21, 2026
   Written for Mike, for the relay, with full liberty taken.
