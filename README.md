# Pattern Pilot

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Validate](https://github.com/Igypop78/pattern-pilot/actions/workflows/validate.yml/badge.svg)](https://github.com/Igypop78/pattern-pilot/actions/workflows/validate.yml)

**Pattern Pilot learns what people in your home do by hand and suggests automations for it.**
It finds routines ("every workday around 6:40 someone turns on the bathroom light"),
sequences ("after the shower the fan goes on") and conditions ("only when it is dark"),
tests each idea against your own history and shows it with the evidence.
Nothing runs until you press *Accept*. Everything stays local – no cloud, no LLM required.

> **Status: v0.1 – data collection.** This version only records. Suggestions arrive in v0.2+,
> once there are ~3 weeks of data. Install it now so it has something to learn from.

## How it works

1. **Collects** state changes of the domains and areas you choose and works out **who** did it:
   a person in the app, a wall switch, an automation, another integration or a device.
2. **Detects household events** instead of storing raw sensor values: shower (humidity rises fast),
   appliance (power jumps), water use.
3. **Remembers context** with every manual action: workday or weekend, day or night, illuminance,
   outdoor temperature, how many people are home.
4. Keeps its **own history** (`/config/pattern_pilot.db`, default 120 days) – independent of the recorder,
   whose default 10 days is too short to find habits.
5. *(v0.2+)* Nightly analysis → suggestions → backtest → card with **Accept / Edit / Not now / Never**.

## Installation

1. HACS → ⋮ → **Custom repositories** → `https://github.com/Igypop78/pattern-pilot`, type **Integration**.
2. Install **Pattern Pilot** and restart Home Assistant.
3. Settings → Devices & services → **Add integration** → *Pattern Pilot*.

## Setup wizard

| Step | What you choose |
|---|---|
| Welcome | how long to keep history, time of the nightly analysis |
| What to watch | domains, areas (empty = whole house), excluded entities, users that are not people (Node-RED, AppDaemon) |
| Signals | bathroom humidity sensors, power sensors, water meter – with thresholds |
| Context | workday sensor, illuminance, outdoor temperature |

Everything can be changed later under **Configure**.

## Entities (v0.1)

| Entity | Meaning |
|---|---|
| `sensor.pattern_pilot_status` | `collecting` / `ready` (≥ 21 days), attributes with counts |
| `sensor.pattern_pilot_days_of_data` | days of history |
| `sensor.pattern_pilot_events` | events in the database |
| `sensor.pattern_pilot_events_today` | events recorded today |
| `sensor.pattern_pilot_manual_actions_today` | manual actions today |
| `sensor.pattern_pilot_database_size` | database size (diagnostic) |

## Privacy

All data stays in your Home Assistant config folder. Nothing is sent anywhere.

## Roadmap

- **v0.2** time-of-day habits + backtest
- **v0.3** card *Igy Pattern Pilot* (in [igy-cards](https://github.com/Igypop78/igy-cards)), Accept → automation
- **v0.4** sequences ("after A, B") and conditions
- **v0.5** routines as triggers, improving existing automations
- **v0.6** forgotten things (lights left on), English + Slovak polish

---

### Slovensky

Pattern Pilot sleduje, čo ľudia v dome robia ručne, učí sa rutiny a navrhuje automatizácie –
s dôkazom z tvojej vlastnej histórie. Nič nespúšťa sám, všetko ostáva doma.
Verzia 0.1 zatiaľ len zbiera dáta; návrhy prídu od v0.2 po ~3 týždňoch zberu.
