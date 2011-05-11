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

[mb]: http://musicbrainz.org/

### Can the service identify short audio snippets?

No, it can't. The service has been designed for identifying full audio files.
We would like to eventually support also this use case, but it's not a priority
at the moment.

### Why do I need to log in to submit fingerprints?

We want to be able to track fingerprint submission for statistical and
data quality reasons. If every user has an unique API key, we can generate 
list of top contributors and similar statistics. Additionally, if we need 
to do some data cleanup, it's much easier to do if we know the source of 
the data. You can use any [OpenID][oid] provider to log in or you can use your 
existing MusicBrainz user account.

[oid]: http://openid.net/

### How can I know you will not do something bad with my MusicBrainz password?

We need the password to verify that you own the MusicBrainz account. 
Currently, MusicBrainz doesn't provide a way to do this without knowing the 
password on our side (OpenID, OAuth or a similar authentication scheme). 
Since the Acoustid database depends heavily on the MusicBrainz database, 
we really wanted to re-use existing user accounts. The only way to do this 
at the moment is to ask the user for both the username and password. We do 
not store the password anywhere, it is transmitted to our server over an 
[SSL tunel][ssl] and it's sent to the MusicBrainz web service for
authentication in a [hashed form][auth]. After it's verified that the 
username and password match, we only store the username.
The server code is [open source][code], so you can check all this by yourself.

[ssl]: http://en.wikipedia.org/wiki/HTTP_Secure
[auth]: http://en.wikipedia.org/wiki/Digest_access_authentication
[code]: https://github.com/lalinsky/acoustid-server/blob/master/acoustid/website.py
