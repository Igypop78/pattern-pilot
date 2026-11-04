# Changelog

## [0.1.3] – 2026-11-04

More accurate "who did it":
- **Commands paired with late confirmations.** Zigbee2MQTT, MQTT and cloud devices report their new state
  a moment later without the original context – it used to look like a wall switch. Now the state is
  credited to whoever sent the command within 10 s (automation, you in the app, another integration).
  Targets by entity, device and area are resolved.
- **Impulses counted once.** A switch that goes on and back off by itself within 5 s (gate, doorbell) is one action, not two.
- **"Outside HA"** instead of "switches": a change without a command from HA (wall switch, remote,
  vendor app). It counts as a manual action only for lights, switches, covers, fans, media players,
  locks and valves. Thermostats, vacuums … changing on their own are **device programs**.
  Existing records are reclassified automatically.
- Card: *Who runs the house* shows *outside HA* and *device programs* (hover explains each),
  labels no longer wrap.

## [0.1.2] – 2026-11-04

- **Igy Pattern Pilot Card** is part of the integration – it registers itself, no files or resources to add.
  Add it from *Add card → Igy Pattern Pilot Card*. Shows:
  - learning progress (day X of 21, when suggestions start), events, learned sensors, Energy meters, database size,
  - events today, manual actions today, sensor changes in the last 7 days,
  - **daily rhythm** – manual actions per hour today vs. the average of previous days,
  - **who runs the house** – you in the app, wall switches, automations, other integrations,
  - **most often by hand** – candidates for automation,
  - **just happened** – latest events, overridden automations marked.
- WebSocket command `pattern_pilot/overview` for the card.

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
