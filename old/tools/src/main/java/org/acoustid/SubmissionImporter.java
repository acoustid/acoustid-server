// Acoustid -- Audio fingerprint lookup server
// Copyright (C) 2010  Lukas Lalinsky
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program.  If not, see <http://www.gnu.org/licenses/>.
package org.acoustid;

import com.google.inject.Inject;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import org.acoustid.data.DataException;
import org.acoustid.data.FingerprintData;
import org.acoustid.data.SubmissionData;
import org.acoustid.data.TrackData;
import org.acoustid.data.Transaction;
import org.acoustid.musicbrainz.MusicBrainzTrack;
import org.acoustid.musicbrainz.data.MusicBrainzPUIDData;
import org.apache.commons.lang.StringUtils;
import org.apache.log4j.Logger;

public class SubmissionImporter {

    private static final Logger logger = Logger.getLogger(SubmissionImporter.class);
    private FingerprintData fingerprintData;
    private TrackData trackData;
    private SubmissionData submissionData;
    private MusicBrainzPUIDData puidData;
    private Transaction transaction;
    private double trackMergeThreshold = 0.7;
    private double fingerprintMergeThreshold = 0.95;

    @Inject
    public SubmissionImporter(FingerprintData fingerprintData, TrackData trackData) {
        this.fingerprintData = fingerprintData;
        this.trackData = trackData;
    }

    @Inject(optional=true)
    public void setTrackMergeThreshold(double trackMergeThreshold) {
        this.trackMergeThreshold = trackMergeThreshold;
    }

    @Inject(optional=true)
    public void setFingerprintMergeThreshold(double fingerprintMergeThreshold) {
        this.fingerprintMergeThreshold = fingerprintMergeThreshold;
    }

    @Inject
    public void setTransaction(Transaction transaction) {
        this.transaction = transaction;
    }

    @Inject
    public void setSubmissionData(SubmissionData submissionData) {
        this.submissionData = submissionData;
    }

    @Inject
    public void setMusicBrainzPUIDData(MusicBrainzPUIDData puidData) {
        this.puidData = puidData;
    }

    /**
     * Load a number of unhandled submissions from the given SubmissionData
     * instance, import them into the main database and mark them as handled.
     * 
     * The Transaction is committed after each import.
     *
     * @param count number of submissions to import
     * @throws SQLException
     * @throws DataException
     */
    public void importSubmissions(int count) throws SQLException, DataException {
        List<Submission> submissions = submissionData.findUnhandled(count, false);
        for (Submission submission: submissions) {
            importSubmission(submission);
            submissionData.markAsHandled(submission.getId());
        }
        transaction.commit();
        logger.info("Imported " + submissions.size() + " submissions");
    }

    /**
     * Import the specified submission into the main database.
     *
     * @param submission submission to import
     * @throws SQLException
     */
    public void importSubmission(Submission submission) throws SQLException {
        List<String> mbids = new ArrayList<String>();
        if (submission.getMBID() != null) {
            mbids.add(submission.getMBID());
        }
        if (submission.getPUID() != null) {
            int minLength = submission.getLength() - 7;
            int maxLength = submission.getLength() + 7;
            List<MusicBrainzTrack> tracks = puidData.findTracks(submission.getPUID(), minLength, maxLength);
            for (MusicBrainzTrack track : tracks) {
                mbids.add(track.getMBID());
            }
        }

        logger.info("Importing submission " + submission.getId() + " with MBID " + StringUtils.join(mbids, ", "));

        Fingerprint fingerprint = Fingerprint.createFromSubmission(submission);

        // See if there is an existing fingerprint or track that we can re-use
        List<FingerprintSearchResult> results = fingerprintData.search(submission.getLength(), submission.getData(), 1, trackMergeThreshold, fingerprintMergeThreshold, true);
        if (!results.isEmpty()) {
            FingerprintSearchResult result = results.get(0);
            logger.debug("Matched " + results.size() + " results, the top result (" + result.getFingerprintId() + ") is " + (100 * result.getScore())+ "% similar");
            if (result.getScore() > trackMergeThreshold || result.getScore() > fingerprintMergeThreshold) {
                fingerprint.setTrackId(result.getTrackId());
                if (result.getScore() > fingerprintMergeThreshold) {
                    fingerprint.setId(result.getFingerprintId());
                }
            }
        }

        // Create a new track
        if (fingerprint.getTrackId() == 0) {
            Track track = new Track();
            trackData.insert(track);
            fingerprint.setTrackId(track.getId());
            logger.info("Added new track " + track.getId());
        }

        // Create a new fingerprint
        if (fingerprint.getId() == 0) {
            fingerprintData.insert(fingerprint);
            logger.info("Added new fingerprint " + fingerprint.getId());
        }

        // Add the MBIDs to the fingerprint's track
        for (String mbid : mbids) {
            if (trackData.insertMBID(fingerprint.getTrackId(), mbid)) {
                logger.info("Added MBID " + mbid + " to track " + fingerprint.getTrackId());
            }
        }
    }

}
