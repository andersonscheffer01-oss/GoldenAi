# Jarvis Robot Matcher Precursor Map

B4.2 does not create a Robot-to-Market matcher. It exposes only the fields a
future empirical design may need:

| Field | Current source | B4.2 state |
|---|---|---|
| regime | scanner / market context | precursor |
| setup | scanner | precursor |
| strategy type | scanner mode | precursor |
| symbol/timeframe | request and scanner | available when observed |
| volatility/spread/session | scanner/technical state | source-dependent |
| risk | risk read model | source-dependent |
| validation | validation trace | historical/source-dependent |
| performance | labeled history summary | sample-limited |

The missing pieces are an empirical association policy, controlled training
or evaluation dataset, confidence calibration, temporal leakage controls and
an explicit approval boundary. No matcher is implied by a precursor field.
