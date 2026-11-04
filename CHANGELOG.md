# Changelog

## [0.1.1] – 2026-11-04

Universal and without questions – nothing has to be chosen by hand.

- **One change detector for any measured sensor** (humidity, temperature, power, illuminance, CO₂,
  air quality, sound, flow) instead of shower / appliance / water. Every sensor first learns its
  normal variation (1 day), then sudden **rises and falls** are stored. Learned values survive restarts.
- **Counters from the Energy dashboard** (grid, solar, battery, gas, water, devices) → consumption
  starts / ends.
- **Automatic context:** workday / weekend / public holiday (country set in Home Assistant),
  sun elevation, outdoor temperature from a weather entity, people at home.
- Setup wizard shortened to *Welcome → What to watch*. New option **sensitivity** (low / medium / high).
- Settings of 0.1.0 are migrated automatically, collected data is kept.
- Integration icon (Home Assistant 2026.3+).

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
