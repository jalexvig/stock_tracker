# Stock Tracker

Stock tracker is a web app that allows users to track a set of stocks with google sheets. [Check it out](https://vatic-interview-alex.appspot.com/)!

Email notifications are disabled by default, but can be enabled in the settings page.

# For Developers

The yahoo finance API is currently queried for price updates but this can easily be changed in `stocks.py`.

This stock tracker web app was built for deployment on [Google App Engine](https://cloud.google.com/appengine/docs/python/) (GAE), but can be modified for other deployment environments by writing custom `db.py` and `emails.py` scripts.

GAE allows for setup of cron jobs (see `cron.yaml` for details). If you are not using GAE, you will need to schedule the execution of `refresh_data.update_all_stocks_sheets`.

### GAE Setup

The GAE SDK can be downloaded [here](https://cloud.google.com/appengine/downloads). Check out the [quickstart](https://cloud.google.com/appengine/docs/python/quickstart) for a brief tutorial.

After [creating a project](https://console.cloud.google.com/project) (note your application ID for later), follow the [instructions](https://developers.google.com/identity/protocols/OAuth2WebServer#creatingcred) to download credentials needed for users to authorize your app. Rename this file `client_secret.json` and place it in your root project folder. Also, make sure that the redirect uris you set up point to your oauth callback endpoint. By default this should be `https://YOUR-APPLICATION-ID.appspot.com/oauth2callback`.

You will also need to enable use of the Sheets API in the [cloud console](https://console.cloud.google.com/apis/library).

Update the `app.yaml` file with your application id.

Deploy using the GAE SDK GUI or a terminal: `appcfg.py update /path/to/project`.

Enjoy.
