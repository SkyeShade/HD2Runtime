# ConcussiveDrumMagazine

Changes the AR-23C Liberator Concussive's default drum magazine attachment from 60 to 90 rounds
through the typed magazine-attachment API. The value is owned by the attachment's entity delta, so
the edit applies to every weapon that equips that drum. `allow_unverified_effect` is required
because re-application at weapon construction is not yet gameplay-proven. Built only; never deployed
or launched.
