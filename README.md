# iCloud Lite

A stripped-down Home Assistant integration that tracks the Apple devices **you pick** using Apple's Find My service. Nothing else.

Inspired by [iCloud3](https://github.com/gcobb321/icloud3), but built from scratch and much smaller.

## What it does

- Creates a `device_tracker` entity for each iPhone, iPad, or Apple Watch you choose
- Reports GPS location, accuracy, and battery level
- Works with Home Assistant's normal zones (Home, Work, etc.)
- Add or remove devices anytime from the integration's **Configure** button
- Set your own update interval (1 to 60 minutes, default 5)

## What it doesn't do (on purpose)

- No dashboard builder
- No Event Log card
- No stationary zones
- No smart or distance-based polling
- No Waze travel time, zone logs, or extra sensors

If you want all of that, use iCloud3.

## Install

### HACS (custom repository)

1. HACS > three-dot menu > **Custom repositories**
2. Add `https://github.com/YOUR_GITHUB_USERNAME/icloud_lite` as type **Integration**
3. Download **iCloud Lite**, then fully restart Home Assistant

### Manual

1. Copy the `custom_components/icloud_lite` folder into your Home Assistant `config/custom_components/` folder
2. Fully restart Home Assistant

## Setup

1. **Settings > Devices & Services > Add Integration > iCloud Lite**
2. Enter your Apple ID and password
3. Enter the 6-digit code that appears on one of your trusted Apple devices
4. Tick the devices you want to track and choose an update interval

To change devices or the interval later: **iCloud Lite > Configure**. Unticked devices have their trackers removed.

## Notes

- Apple asks for a new 2FA code every so often. When that happens, Home Assistant shows a **Reauthenticate** prompt. Just repeat the code step.
- Polling too often drains device batteries and can get you rate-limited by Apple. Stick with 5 minutes or higher unless you have a reason.
- If a device is offline, the last known location is kept.
- Devices without the Home Assistant Companion app are where this shines. If a phone already has the Companion app, that's usually more accurate and needs no Apple login.
- Uses the [pyicloud](https://github.com/timlaing/pyicloud) library, same as Home Assistant's built-in iCloud integration.

## Troubleshooting

Go to **Settings > System > Logs** and search for `icloud_lite`. Include that output when opening an issue.

## Disclaimer

Not affiliated with or endorsed by Apple or the iCloud3 project. Use at your own risk.

## License

MIT
