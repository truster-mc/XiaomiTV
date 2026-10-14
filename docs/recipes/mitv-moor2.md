# Recipe: Xiaomi MiTV-MOOR2 (MI TV A2 family, Google TV, Android 11)

What was changed on this TV, in order, why, and how to undo each step. Everything below used
`pm disable-user --user 0` (reversible, no root). Use the web tool for the apps; each apply
saves a backup in `backups/` first.

## The TV
- Model `MiTV-MOOR2`, Xiaomi, Android 11 (API 30), Google TV home (`launcherx`), MediaTek
- 1.8 GB RAM, 4 cores, 4 GB `/data`; ADB over Wi-Fi on `192.168.1.6:5555`
- Fixtures captured from this TV are in `tests/fixtures/`

## Result (free memory after a fresh reboot)

| Stage | Free RAM |
|---|---|
| Start | 822 MB |
| After step 1 (8 safe apps) | 834 MB |
| Projectivy as home, Google launcher still running | 907–920 MB |
| After steps 2-4 (all below) | **1,016 MB** |

Swap use also dropped to about 15 MB of 600 MB.

## Step 1: safe apps (telemetry, promo, setup leftovers)
`com.mitv.tvhome.atv` (PatchWall; not working in this region), `com.xiaomi.mitv.updateservice`,
`com.miui.tv.analytics`, `com.google.android.onetimeinitializer`,
`com.mstar.android.tv.disclaimercustomization`, `com.xiaomi.statistic`,
`com.mitv.tvhome.michannel`, `com.google.android.play.games`.
Already disabled at the start: `com.mitv.tvhome.mitvplus`, `com.amazon.amazonvideo.livingroom`,
`com.google.android.youtube.tvmusic`. Frees little RAM (about 36 MB).

## Step 2: more safe apps and trade-offs the owner chose
- Safe: `com.android.printspooler`, `com.android.dreams.basic`, `com.google.android.feedback`,
  `com.google.android.syncadapters.calendar`.
- Trade-offs accepted, with what stops working:
  - `com.netflix.ninja`, `com.amazon.amazonvideo.livingroom`: those apps and their remote buttons
  - `com.google.android.tv.remote.service`: phone-as-remote and pairing new Bluetooth devices
  - `com.xiaomi.mitv.smartshare`: Miracast screen mirroring
  - `com.google.android.tts`: Google speech services
  - `com.mediatek.tv.service`: the 5 AM self-test wake-up, but also the sleep timer
  - `com.google.android.marvin.talkback`: the screen reader
  - `com.google.android.katniss` (Google Assistant, about 60-100 MB): **the remote's microphone
    button and voice search stop working**
  - `com.google.android.tungsten.setupwraith`: setup wizard; can act as a launcher fallback

## Step 3: replace the home screen (the biggest single saving)
The Google TV launcher (`com.google.android.apps.tv.launcherx`) used about 90-115 MB plus its
`coreservices` process. Projectivy Launcher used about 47-60 MB.
1. Install **Projectivy Launcher** from the Play Store or the developer's official GitHub release.
   Do not use modified builds: the launcher gets an accessibility permission.
2. Enable its accessibility service (TV: Settings > System > Accessibility). Over ADB the
   service is `com.spocky.projengmenu/.services.ProjectivyAccessibilityService`.
3. In Projectivy turn on the Home button override and check Home opens it.
4. Back up, then disable `com.google.android.apps.tv.launcherx` (the tool needs the `--force`
   launch flag because it rates the Google launcher "keep"). `setupwraith` must be disabled too.
   With the Google launcher gone, the system resolves Home to Projectivy directly.
5. Reboot and confirm the TV boots to Projectivy.

## Tried, did not hold
- **Cached-app freezer** (`settings put global cached_apps_freezer enabled`, plus
  `device_config put activity_manager_native_boot use_freezer true` and
  `freeze_debounce_timeout 1000`): the two `device_config` values were back to unset after
  a reboot, so it does not persist. Probably reset by Play Services at boot (not confirmed).
  Left off.

## Left alone on purpose
- `com.google.android.gms` (Play Services, about 115 MB) and `com.android.vending`: needed for
  sign-in, app installs and updates.
- `com.mitv.livetv` and Live TV setup: also manage the HDMI inputs.
- `com.xiaomi.mitv.tvmanager`, `com.xiaomi.mitv.mediaexplorer`, `com.google.android.apps.mediashell`
  (Chromecast built-in).

## Undo
- One app: `adb -s 192.168.1.6:5555 shell pm enable --user 0 <package>`
- Back to a snapshot: the web tool's Backups list, Restore.
- Google launcher: `pm enable --user 0 com.google.android.apps.tv.launcherx`
- Then reboot. If Home shows nothing, `com.android.tv.settings` provides a fallback home.

## Maintenance
- Firmware updates can bring apps back, including the Google launcher. Scan again after any
  update; the page flags apps that came back.
- Reboot before judging speed. Turn USB debugging off when finished (one forum report of
  USB ports misbehaving with it left on).

## Sources
- 4pda "Xiaomi MI TV A2" thread, shtopor-89's app list (post 126227739) and meth_lab (post 121276741)
- Habr write-up on a Xiaomi Mi TV debloat (habr.com/ru/articles/1044486)
- (не)Честно о технологиях, "How to speed up Android TV" (dzen.ru/a/aoWbWa8XvD76H563)
