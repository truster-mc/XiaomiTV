# Recipe: Xiaomi MiTV-MOOR2 (MI TV A2 family), Google TV, Android 11

The recipe now lives as data in
[`xiaomitv/data/recipes/mitv-moor2-android11.yaml`](../../xiaomitv/data/recipes/mitv-moor2-android11.yaml).
It is shown in the web page's **Recipes** card, filtered by model and Android version. Click a
recipe after a scan and the page ticks every app from it that your TV has.

To add a recipe for another TV, copy that YAML file, change `id`, `models`, `android` and the steps,
and run `python -m pytest`; the tests check the format and every package name.

Result on the original TV: free RAM went from 822 MB to about 1,016 MB after a fresh reboot.
