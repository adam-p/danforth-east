Neighbourhood Community Association Membership Management
=========================================================

Sales Pitch
-----------

Have you agreed to help a local organization register, renew, and keep track of members -- and then realized it's more work than you expected? Me too! This system can be run for free on Google App Engine and uses Google Spreadsheets as its database. It's easy for organization managers and members, mostly self-maintaining (for your sanity), and pretty flexible and powerful (for when you inevitably get asked to add new features).


Overview
--------

This is a Google App Engine application (and web interface) written for my neighbourhood community association to help register and keep track of its few hundred members. It's largely bespoke -- it could certainly be adapted to a different organization, but it's not (yet) cleanly parameterized. It uses Google Spreadsheets as the database, which might be somewhat novel, and might be of use to someone.

Demo
----

The demo management site is located at: https://mmbrmgmt.appspot.com

The demo form-embedded-in-organization-website page is located at: https://s3.amazonaws.com/mmbrmgmt/iframe-test-custom.html

The spreadsheets acting as the "database" for this demo are:

* [Members](https://docs.google.com/spreadsheets/d/1CEC4cAoA4SoVZQ-trkFzy6Mi5tL42vuyWyMIts3hMQ8/edit?usp=sharing)
* [Volunteers](https://docs.google.com/spreadsheets/d/1BZLJtMlzg1E1WGIDCEEmWFJoUTg3fdZquXaqa7-Vf4E/edit?usp=sharing)
* [Volunteer Interest Areas](https://docs.google.com/spreadsheets/d/1NRMFHCF_9dEyizfdO2vxWXUNojLYNVc5uwFOGCHp6iA/edit?usp=sharing)
* [Skills Categories](https://docs.google.com/spreadsheets/d/1hLNeUZA7v9K5608HF-B_jMa0VFmLo8OpHi3Js-YAeao/edit?usp=sharing)
* [Authorized Users](https://docs.google.com/spreadsheets/d/19eGfHsDx70tHcufLNmA3lXW4KcWTMZPDIccNnLlTYfw/edit?usp=sharing) (not used in demo)


Introduction
------------

The [Danforth East Community Association](http://deca.to/) asked me to help update their/our membership management system. They had been using pieces of paper with new member info, an Excel spreadsheet on someone's computer, and manual responses to PayPal notification email.

The requirements were/are something like:

* There are a few hundred members.
* There are about 12 association managers.
* People register online and in-the-field (mostly at the local farmers' market).
  - When joining online, people pay with PayPal or indicate that they'll mail/deliver cheque or cash later.
  - When joining at the farmers' market, member typically hands over cash.
* Some volunteer management help would be nice to have.
* Mapping of member locations would be nice to have.
* It would be nice to be able to register people at the farmers' market on an iPad, etc.

And some self-imposed requirements:

* If I get hit by a truck, non-devs should be at least able to salvage the data.
* I didn't want to become the webmaster of the association website.

I looked into existing solutions and didn't find much. [CiviCRM](https://civicrm.org/) is very interesting, but it seemed like overkill, and it seemed like a lot of learning and training. (Of course, in retrospect, it would have been less work to do the learning and training.)

I decided early on that a Google Spreadsheets-centric approach would be good. The spreadsheet could be shared among the association manager and people are pretty comfortable with spreadsheets. I fooled around with Google Apps Script-based approaches, but I found them frustrating and limiting: because of the [Caja](https://code.google.com/p/google-caja/) sandboxing, debugging and developing are painful and slow, and deployment options are limited, and there are limitations in what you can get done in it. Google Apps Script is very cool and easy for small tasks, but creating a multi-faceted web-based UI with future flexibility seemed like it wasn't going to work out.

So I settled on using Google App Engine (GAE), with Google Spreadsheets as the database.


How it works
------------

From the user side, there are two aspects to the system: there is the publicly accessible self-registration form and there is the authorized access to direct member joining, renewal, mapping, etc.

On the back end, there's some fairly simple [CRUD](http://en.wikipedia.org/wiki/Create,_read,_update_and_delete)-ish code made more complicated by the fact that instead of a local database it's talking to the Google Spreadsheets API. There's also application logic around processing [PayPal IPNs](https://developer.paypal.com/webapps/developer/docs/classic/products/instant-payment-notification/), emailing new member and volunteeer managers, culling defunct members, and so on.

### Spreadsheets?

I wanted the "database" to be human readable/understandable/exportable/manipulable. People seem pretty comfortable with spreadsheets (the old membership list was kept in one). Some experimentation showed that the speed of accessing spreadsheet data with every request was acceptable (for the size of data in question), and I figured I could add caching of the data (on either or both of the server or client) if needed.

So here is a rough flow of what happens when a member is directly registered by an association manager:

1. Manager requests the `/new-member` page.
2. Server fetches authorization spreadsheet and checks that the manager's email address is in it.
3. Server fetches the "volunteer interest areas" spreadsheet and templates those values into the form.
4. Server returns the page to the manager.
5. Manager fills in the form and submits it.
6. Server again fetches and checks authorization against spreadsheet.
7. Server checks to see if the new member's email address matches any already existing member. (Triggering a renewal flow if it does.)
8. Server writes a new row to the spreadsheet with the new member information.

Loading the `/new-member` page takes about 420ms. The creation of a user takes about 440ms. These aren't blazing fast numbers, but they're acceptable for this website, and that's without any caching or other optimization efforts.

Retrieving a JSON'd list of all member data (for 200 members) takes about 1000ms. This isn't great, but it's done via AJAX and it's tolerable.

(In the GAE test environment, there are pretty frequent invalid certificate errors when trying to access the Spreadsheets API. In the real GAE environment I'm not sure I've ever seen them.)

### `iframe`ing the self-serve registration

Registration of new members needed to be done on the website, but I didn't (and don't) have edit access to the organization's website. And... I don't really want access. So I decided that the form would have to be able to live in an `iframe`. That way I could just provide a few lines of code/HTML to the webmaster who could then embed it. I would still be able to fix/improve the form without touching the website.

This has worked pretty well, but there are some shortcomings:

* The style matching between `iframe` and parent is a bit weak, but passable. It could be made better by including a CSS file provided by the webmaster/designer.
* The modal wait dialog when sending the member information is only in the `iframe`.
* The loading of the `iframe` isn't super fast. Sometime I'll look at optimizing general site speed and maybe add a load message/spinner in the `iframe`.


Setup
-----

Please file and issue or pull request if encounter a problem with these steps (or even if you don't and it just goes smoothly).

### Get the code

Clone this repo (or fork, which you'll want to do eventually). Install the [Google App Engine SDK for Python](https://developers.google.com/appengine/downloads).

Open a terminal in the repo root directory and run:

```
pip install -r requirements.txt -t lib/
```

Rename `config/private.py.sample` to `config/private.py` (Henceforth referred to as `private.py`.) Leave that file open, since you'll be editing it.


### Google account stuff

I created a brand new Google/Gmail account to the be owner of the GAE project and spreadsheets. Any of the organization managers might move or quit, so I figured it would be best to have an account that separate from any one person.

You probably want to set up mail forwarding from that new account to your own, at least for now.

Henceforth I'll be assuming that you're logged in with and using that account. However, you can do stuff like adding your personal account as an admin of the GAE project, which allows you to do a lot without logging in as the other account.

In `private.py` set `MASTER_EMAIL_ADDRESS` to the account email address. Also add the email to the `ALLOWED_EMAIL_TO_ADDRESSES` list.


### App Engine project

Create your new GAE project. Probably via [here](https://console.developers.google.com/project). Edit `app.yaml` and replace the `application` value with whatever you picked as your GAE project name.

When that is complete, click on the "Enable an API" button, or "APIs & Auth/APIs" in the left sidebar. Then enable Drive API, Drive SDK, Geocoding API, and Google Maps JavaScript API v3. [Note: Not sure Drive SDK is necessary.]

Click on "Credentials" in the left sidebar. Click on "Create new Client ID", then "Service account", then "Create Client ID". A JSON file with the new credentials and key will download. Save the contents of the `private_key` field to a file named `privatekey.pem` in the root of your source directory (replacing `\n` with actual newlines). Copy the `client_email` value and set as `SERVICE_ACCOUNT_EMAIL` in `private.py`.

[Note: I think there's a default service account for the GAE project, but I couldn't figure out how to get the key for it. Maybe instead you generate and upload its key?]

Under "Public API access" click on "Create new Key". Click on "Server key". Leave the IP address field blank (for now). Copy the new "API Key" and set as `GOOGLE_SERVER_API_KEY` in `private.py`.

Under "Public API access" click on "Create new Key". Click on "Browser key". Leave the referrers field blank (for now). Copy the new "API Key" and set as `GOOGLE_BROWSER_API_KEY` in `private.py`.


### Google Drive

In that account, go to Google Drive and create a new folder. Share that folder with edit permissions with:

- The `SERVICE_ACCOUNT_EMAIL` from `private.py`.
- Your own personal email address.
- Whomever else is going to managing members.

In that folder you will be creating the "database" spreadsheets. Open `config/__init__.py` to see what fields they should have. Create these spreadsheets (the name isn't actually important, but it'll be easier if you follow what's here):
- Create a spreadsheet called "Authorized users" and create columns headers with the names in `AUTHORIZED_FIELDS`.
- Create "Members" with the column headers from `MEMBER_FIELDS`.
- Create "Volunteers" with the column headers from `VOLUNTEER_FIELDS`.
- Create "Volunteer Interest Areas" with the column headers from `VOLUNTEER_INTEREST_FIELDS`.
- Create "Skills Categories" with the column headers from `SKILLS_CATEGORY_FIELDS`.

In the "Authorized users" sheet, add your personal email address and `test@example.com`. Also add a few entries to "Volunteer Interest Areas".

For each spreadsheet, copy the big random-looking value from the URL and paste that value into the appropriate `*_SPREADSHEET_KEY`.

To get the keys for the first worksheet of each of those spreadsheets, run this command:

```
python first_sheet_keys.py
```

Put the values it prints into the appropriate `*_WORKSHEET_KEY`. (For brand new spreadsheets they will probably be all the same value, and the same as the values already in `private.py` and you'll think this step is silly. But if you mess around with creating and deleting sheets the values will change.)


### Try out the management site

We're not done configuring stuff yet, but you can try out some of the functionality now.

Run the Google App Engine Launcher that got installed with the GAE SDK. (Or use the command line interface.) Add the root of your source directory as an "existing application". Run the application and open the logs viewer.

In your web browser, go to `http://localhost:8080/`. You should see the management site main page. You'll be prompted to share your location with the site -- agree.

Click on "Register New Member". You'll be prompted to enter an email to log in as -- just leave it as `test@example.com` for now. Click Login. (Later you'll want to check the "Sign in as Administrator" box so you can manually trigger cron jobs and the like.)

You'll now be on the "Create New Member" page. Note that values you put in the "Volunteer Interest Areas" sheet appear. Fill in the form and submit it. It should be successful.

Check the "Members" spreadsheet to see that your new member has been added. Be sure to scroll all the way to the right to see everything that's getting filled in.

Take a look at the GAE launcher logs to get acquainted with them.

Fool around with creating more members, renewing them, authorizing new managers, and viewing the members map.


### PayPal

To try out the self-serve interface we're going to get PayPal ready.

PayPal makes it pretty easy to set up a testing sandbox -- you can probably [get started here](https://developer.paypal.com/webapps/developer/applications/accounts). Also create a purchaser account or two (it doesn't matter what email you use for them, but it's handy if you use another address you own, for a more realistic workflow).

Log into [www.sandbox.paypal.com](https://www.sandbox.paypal.com) with the sandbox facilitator/merchant account. Create a button for a subscription. Set the subscription period to a day, so it's easier to see the effects of automatic PayPal subscription payments. Set the price to whatever you want. The value you give to the button's "item name" must be copied to `PAYPAL_TXN_item_name` in `private.py`. In "Step 3" of the button interface add to the "advanced variables" field `notify_url=https://myproject.appspot.com/self-serve/paypal-ipn` (replacing `myproject` with whatever you named your project, of course).

Save the button. Copy its "Email" URL and set it as `PAYPAL_PAYMENT_URL` in `private.py`. Also set your sandbox facilitator email address to `PAYPAL_TXN_receiver_email`. (Note that `PAYPAL_IPN_VALIDATION_URL` in `config/__init__.py` is already set the sandbox.)

As you noticed, the PayPal IPN URL is pointing to your GAE instance. So we'd better set it up.


### MailChimp

The membership system includes optional MailChimp integration, so it can be used for emailing Members and Volunteers.

MailChimp integration can be disabled by setting `MAILCHIMP_ENABLED` to `False` (in `config/private.py`). Or configure MailChimp like so:

1. Get your API key: Click on your name in the upper right, then "Account", then "Extras/API Keys". Click the "Create a key" button. Copy the value into `config.MAILCHIMP_API_KEY`.

2. Create a new List. "List", then "Create List".

3. For that list, add these merge fields/tags (these values are specified in the field info in `config/__init__.py`):
   - Leave the default "First Name (FNAME)", "Last Name (LNAME)"
   - Label: "Volunteer Interests". Merge tag: "VOLUNTEER". Type: text.
   - "Skills", "SKILLS", text
   - "Member Type", "MMBR_TYPE", radio buttons with values "Member" and "Volunteer"

4. For the list, go to "Settings/List Name and Defaults". Copy the "List ID" into `config.MAILCHIMP_MEMBERS_LIST_ID`.

5. You may wish to create "Segments" for the list. For example, you could create a segment for "'Volunteer Interests' contains 'Arts Fair'", so you can easily email everyone interested in volunteering for the arts fair.


### Deploy to App Engine

In Google App Engine Launcher click the deploy button (or use the command line stuff). You can authenticate with the credentials of the account that owns the project, or with any account added as an admin (like your personal account).

Test out the deployed project at [https://myproject.appspot.com](https://myproject.appspot.com).

You should also "deploy" `iframe-test.html`. You can put it anywhere that's publicly accessible on the net (I used S3).


### Run the self-serve page and use PayPal

First, take a look at the source for `iframe-test.html`. There's an `iframe` tag and a `script` tag and that's it. It's really just giving us the cross-origin restrictions we're going to face in the actual production deployment.

Go to your publicly hosted `iframe-test.html`. Fill in the form and submit it. You'll be redirected to the `PAYPAL_PAYMENT_URL`. Log in with the sandbox purchaser account your created. Pay for the subscription.

Your new member won't show up in the spreadsheet immediately. The member data has been staged by the server, waiting for confirmation from PayPal that the payment went through.

Take a look the logs for your GAE server: https://console.developers.google.com/project/apps~myproject/appengine/logs (replace "myproject"). Look for errors, and watch for the `/self-serve/paypal-ipn` request to arrive (there might be one or two preliminary requests before the one we're looking for). After that you should see the new member record show up in the Members spreadsheet.

Note that if you test the entire self-serve workflow -- including PayPal -- locally, the IPN will still go to your GAE instance. (Well, unless you point a domain at your home IP and port-forward to your local server.)


### Finishing steps

There are occurences of branding in files that aren't yet properly parameterized, so you should search for "deca" or "danforth" in source files for strings you should change for your own organization.

* Replace the contents of `templates/tasks/email-*` files to match your community organization.

* Change the timezone in `cron.yaml` and `config/__init__.py` to your own. List of [possible timezones here](http://en.wikipedia.org/wiki/List_of_zoneinfo_time_zones).

* You might want to change "Postal Code" to your local equivalent.

* The member form has a "Toronto" default value for city.

* The member form has a Toronto-ish placeholder for postal code.

* If you don't have a farmers' market in your neighbourhood, you'll probably want to change or remove that option.

* If your heathen country uses "check" instead of "cheque", I... I just don't know.


Production steps
----------------

First of all, after changing your config to production values you're going to have to be careful about further development and testing and about not deploying debug settings. You can probably use GAE's support for [multiple application versions](https://gae-php-tips.appspot.com/2013/06/25/harnessing-the-power-of-versions-on-app-engine/) to help.

* PayPal stuff:
  - Change `config.PAYPAL_IPN_VALIDATION_URL` to the non-`sandbox` URL.
  - Change `config.PAYPAL_PAYMENT_URL` to the URL of your real PayPal button. And make sure that button is configured properly (double-check the `notify_url`).
  - Change `config.PAYPAL_TXN_receiver_email` to your real PayPal account email.
  - Double-check `config.PAYPAL_TXN_item_name`.

* Change `config.DEBUG` to `False`.
  - Note that this will automatically disable the `ALLOWED_EMAIL_TO_ADDRESSES` restriction.

* Make sure `config.ALLOWED_EMBED_REFERERS` is set properly. Except... we don't use it at all right now, so never mind.

* For your Google API keys, the "APIs & Auth/Credentials" console: properly set allowed referers for the browser key and allowed IPs for the server key.


Instructions to Organization Managers
-------------------------------------

This system is designed to be easy for the organization managers to use. That being said, there are some things that need to known by them:

* Do not rename columns.
  - If you need to rename a column, talk to the dev first.
  - It's fine to re-order columns or add new columns.

* In the "Authorization" spreadsheet, the "Email" values must be the "real" (canonical) forms. For example, if you log into Gmail with "my.name@gmail.com" then that's the value that must be in the Authorization spreadsheet -- you can't use "my.name+stuff@gmail.com" or the like.

### Instructions to organization admins

This is for the webmaster and/or the controller of the PayPal account.

#### PayPal

* If you have already been using a PayPal button for accepting subscriptions:

  Set your account IPN to our new IPN notification URL. In the PayPal web interface go to "My Account / Profile / Selling Preferences / Instant Payment Notification Preferences" (or [this link](https://www.paypal.com/ca/cgi-bin/webscr?cmd=_profile-ipn-notify)). Click "Turn On IPN" (or maybe "Edit Settings"). Set the "Notification URL" to `https://myproject.appspot.com/self-serve/paypal-ipn` (with `myproject` replaced by our real project name). Click "Enabled" and Save.

  - Doing this means that any existing PayPal subscriptions will naturally become part of our new system.

* If you already have an existing subscription button, you can (and should) update it rather than create a new one.

* In "Step 3" of the button interface add to the "advanced variables" field `notify_url=https://myproject.appspot.com/self-serve/paypal-ipn`, with `myproject` replaced by our real project name.

* In "Step 3" of the button interface you should probably set the cancel and success URLs to the organization website. It can just be the root of the site -- nothing fancy.

* On the "button code" page, instead of the `<form>` code, go to the "Email" tab. That's the URL we'll use -- make note of it.

* If you change (or have changed) the subscription price, be sure to let me know.

Things you need to give me for initial setup:

* Our PayPal account email address.

* The PayPal "Email" URL for our button.


#### Site modifications

The new membership form will live in an [`iframe`](https://developer.mozilla.org/en/docs/Web/HTML/Element/iframe) in the organization site.

You will need to remove the existing form and replace it with these two lines of HTML:

```html
<iframe id="member-form" src="https://myproject.appspot.com/self-serve/join" width="100%" scrolling="no"></iframe>
<script type="text/javascript" src="https://myproject.appspot.com/js/self-serve-parent.js"></script>
```

...with `myproject` replaced with the actual name or our project.

If you're curious about the `script` being included: it's used to help with resizing of the form in the page (without scrollbars) and for figuring out where to position a "please wait" dialog.

##### Page width check

At maximum width, the "first name" and "last name" fields should be beside each other, not on top of each other. If this isn't the case, please let me know.

(Note to self: in `static/vendor/bootstrap/bootstrap-source/less/variables.less` change `@screen-md` to be the actual maximum of the parent page. Then `grunt dist` and test.)


Other Features
--------------

There are a few other features of the system that aren't mentioned above and aren't obvious from playing with the demo.

### Membership archiving

At the start of every year a copy of the Members spreadsheet is made with the name "Members 2013" (e.g.). So there's always a historical record of what the membership looked like in the past. (And we could use that for mapping or whatever.)

### Automatic defunct member culling

When a member's last renewal is two years in the past (that is, they're a year expired) they get removed from the Members spreadsheet. This helps us prevent the members list getting cluttered with people who have moved away, etc.

(Technical note: the amount of time before a defunct member is culled is not well parameterized. See `gapps.cull_members_sheet()`.)

### And more!

Rather than making this README longer than it already is, I'm going to document some features and details in [the wiki](https://github.com/adam-p/danforth-east/wiki).


Future work
-----------

### Features

* Add captcha to self-serve form (or at least to the pay-later option).

* Automatically sign people up for blog post emails.
  - (Lots of complications. Feedburner no longer has an API. Need unsubscribe. Lots of work to roll our own. MailChimp, maybe?)

* If there's a renewal of a not-yet-expired member...? Push the renewal date into the future? But that makes no sense. Maybe "renewed date" should be changed to "expiry date" (or both).
  - Right now a premature renewal doesn't give the member any extra time.

* Add ability to restrict sign-up to a particular set of postal codes. Or maybe a geographic bounding box.

* Map: Add join and renew locations to map.
  - different colours and markers
  - buttons to show/hide
  - add note that there's not much data yet

* When member renews, should volunteer interest area rep get emailed?
  - selected interest areas could change during renewal (in some scenarios)
  - My guess is "no". Too spammy. Add a "peruse potential volunteers" interface instead.

* Offline sign-up. I'm not sure yet how necessary this is, but...
  - Scenario: Signing up members at the Farmers' Market on an iPad that has no network. (Why not just tether? Anyway...)
  - Could do [HTML5 offline](http://www.html5rocks.com/en/features/offline) stuff. (Will need a bit of that for any solution -- to detect offline.)
  - Submitting could detect offline and put data (YAML, JSON) into the body of an email that will get sent next time the device goes back online. (With a GAE auto-receiver.)
    - Should have from-address auth.
  - Offline creation obviously means that the user/member can't be prompted for anything by the server.

* `/renew-member`: Add "member since" and "last renewed" to the member renew form. (The latter is kind of there now, but not visible enough.)


### Technical

* Put the contents of `privatekey.pem` into `private.py` instead of reading from a file.

* Self-serve: Limit non-PayPal sign-ups per day.
  - There isn't yet a "mail in a cheque" option on the self-serve registration, but there probably will be (since there was on the original site). That option removes the money-gate of the PayPal option and introduces the possibility of someone spamming the form and filling the spreadsheet with crap.
  - I think that the "mail in a cheque" option will probably not be super popular, so it's probably safe -- and good -- to add a, say, 10-per-day limit on sign-ups with that option.

* Self-serve: Provide a mechanism for the parent page to provide styling to the form. If the webmaster wants to change the organization site they shouldn't have to talk to me to make the styles match.

* Modify `helpers.BaseHandler` (create a subclass, probably) so that `post()` always does CSRF.

* Create a subclass of `helpers.BaseHandler` to always do user-logged-in checks. (Maybe same subclass as CSRF checks.)
  - Remember that `@check_login` can only be used for `get()`.

* Styling and imagery -- both for customization and handsomeness and usability. Right now it's default Bootstrap. It's even using the HTML5BP favicon.
  - Keep in mind that the self-serve form needs to match embedding site.

* Add load spinner to `iframe` while form is loading. (Is that even possible? Slowness usually comes from our GAE instance starting up. Won't that same slowness affect anything we serve?)

* Make it easier for people to adapt this to other organizations.

* I'm not sure there's much benefit to having the authorization table be in a spreadsheet vs. GAE's NDB. Probably move it there and add some CRUD.

* Make Bootstrap a git submodule, with just `variables.less` under our source control.

* Spreadsheet caching: Speed isn't really a problem yet, for us, but:
  - Avoid spreadsheet reqs blocking any request.
  - Add read and write caching using NBD as intermediary.
  - Use Drive API to detect spreadsheet modifications (maybe in a fast-ish `cron` job -- not blocking request).
  - Move auth to NDB completely (there's another item here for that).
  - Make volunteer interest list stuff AJAX rather than server-side rendered in template.

* Page template caching: Templates that don't have really dynamic content (like, just field names) should not be rendered on each request, just once -- either before deploying (maybe when saving file) or at app start-up time. ("App start-up time" might be bad as well. That happens pretty often and we don't want to add more work.)
  - App start-up time: probably/maybe in `appengine_config.py`
  - the only(?) dynamic thing is the volunteer interest list...?
    - could/should get that list via JS
  - could re-render templates via cron
  - Also, generate some JS config stuff at the same time. Like, 'email' is hardcoded right now. (Look for TODOs in code.)
    - And the paths to '/new-member' and '/renew-member', etc.

* If we have a compile-time or app-start-up-time step, we could add fetching of first worksheet IDs, rather than it being a manual step.
