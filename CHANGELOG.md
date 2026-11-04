# Changelog

## [0.1.0] – 2026-11-04

First version – **data collection only**, no suggestions yet.

- Own event database `/config/pattern_pilot.db`, independent of the recorder (default 120 days).
- Records state changes of chosen domains / areas and who caused them:
  person (app), wall switch, automation / script, other integration, device, excluded user.
- Overrides: a person reverting an automation within 2 minutes is marked.
- Detectors store household events instead of raw values: shower (humidity rise),
  appliance (power jump), water use.
- Context snapshot with every manual action: day type, sun, illuminance, outdoor temperature, people home.
- Setup wizard and options menu (what to watch, signals, context, history and analysis).
- Sensors: status (collecting / ready), days of data, recorded events, events today,
  manual actions today, database size.
- Diagnostics download.
