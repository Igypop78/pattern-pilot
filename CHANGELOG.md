# Changelog

## [0.1.5] – 2026-11-10

Less noise, based on a week of real data (~17 000 events a day):
- **Group entities are skipped.** Light / switch / cover groups, binary sensor groups (whole-house motion,
  windows, doors), sensor groups and Zigbee2MQTT groups only repeat their members – they doubled the
  events and showed up as manual actions (e.g. *Upstairs lights 133×*). Members are recorded as before;
  a command to a group still counts for its members.
- **Zigbee2MQTT groups are matched by unique id** as well (`0x…_light_zigbee2mqtt`,
  `<group id>_light_zigbee2mqtt`) – matching by device identifiers alone found no group on a real system.
  Diagnostics list each group with how many entities were matched.
- **Motion flapping merged.** A binary sensor that turns on again within 60 s after turning off is one
  activity (camera motion, PIR re-triggers).
- **Automation runs throttled.** The same automation is recorded at most once per 10 minutes
  (some ran 800–900 times a day). Which automation changed a device is still recorded with the change.
- **Energy dashboard: consumption only** – grid import, gas, water and individual devices.
  Solar production, battery and export follow the sun and the battery logic, not people.

## [0.1.4] – 2026-11-05

- **Group members.** A command to a **Zigbee2MQTT group** now counts for its member devices too –
  members report their new state separately and used to look like a change outside HA. Groups are
  read from `zigbee2mqtt/bridge/groups` (any base topic) and matched to HA devices automatically.
  Home Assistant groups (light / switch / cover groups, scenes) are expanded the same way.
- **About 60 % smaller database.** Entity ids are stored once, unused columns and one index are gone.
  Existing data is converted automatically on the first start (takes a few seconds).
  With ~10 000 events a day, 120 days of history now take roughly 120 MB instead of 300+ MB.
- Weekly maintenance also shrinks the write-ahead log.
- Diagnostics: entities that produced the most events in the last 24 h, mapped Zigbee2MQTT groups.

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
