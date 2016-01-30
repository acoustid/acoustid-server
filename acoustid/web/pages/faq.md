Title: Frequently Asked Questions

### What is the purpose of this project?

There are several companies that provide audio identification services.
Unfortunately, so far there was none of them published the fingerprint database
and/or the source code for the server architecture.
This project started as an experiment to implement a large-scale and
fully open source audio fingerprinting solution, that can be used by other
open source software without depending on proprietary software. The primary focus is
on integration with the [MusicBrainz][mb] music metadata database. There is a long 
way to go to reach the goal, but you can help by submitting more fingerprints,
helping developing the software or just spreading the word.

[mb]: https://musicbrainz.org/

### Can the service identify short audio snippets?

No, it can't. The service has been designed for identifying full audio files.
We would like to eventually support also this use case, but it's not a priority
at the moment. Note that even when this will be implemented, it will be still
intended for matching the original audio (e.g. for the purpose of tracklisting
a long audio stream), not audio with background noise recorded on a phone.

### Why do I need to log in to submit fingerprints?

We want to be able to track fingerprint submission for statistical and
data quality reasons. If every user has an unique API key, we can generate 
list of top contributors and similar statistics. Additionally, if we need 
to do some data cleanup, it's much easier to do if we know the source of 
the data. You can use any [OpenID][oid] provider to log in or you can use your 
existing MusicBrainz user account.

<span id="api_key_not_working"></span>
### Why is my API key not working?

There are two kinds of API keys. The one you see immediately after logging in is
an [user API key](/api-key) that is meant to be entered into an application like
MusicBrainz Picard for the purpose of identifying yourself or. This is the API
key that needs to be sent to the "submit" endpoint as the "user" parameter.

If you are developing an new application and need an API key for the "client" parameter,
you need an [application API key](/my-applications). You need to
[register your application](/new-application) to get one.

[oid]: http://openid.net/

[code]: https://bitbucket.org/acoustid/acoustid-server/src/master/acoustid/website.py

