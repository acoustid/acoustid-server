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

import java.sql.SQLException;
import org.acoustid.data.DataException;
import org.junit.Test;
import static org.junit.Assert.*;
import static org.mockito.Mockito.*;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import org.acoustid.data.FingerprintData;
import org.acoustid.data.SubmissionData;
import org.acoustid.data.TrackData;
import org.acoustid.data.Transaction;
import org.acoustid.musicbrainz.MusicBrainzTrack;
import org.acoustid.musicbrainz.data.MusicBrainzPUIDData;
import org.junit.Before;
import org.mockito.ArgumentCaptor;
import org.mockito.invocation.InvocationOnMock;
import org.mockito.stubbing.Answer;

public class SubmissionImporterTest {

    private int trackId;
    private int fingerprintId;
    private FingerprintData fingerprintData;
    private TrackData trackData;
    private SubmissionImporter importer;

    class TrackInsertAnswer implements Answer {

        @Override
        public Object answer(InvocationOnMock invocation) throws Throwable {
            Track track = (Track)invocation.getArguments()[0];
            track.setId(++trackId);
            return track.getId();
        }
        
    }

    class FingerprintInsertAnswer implements Answer {

        @Override
        public Object answer(InvocationOnMock invocation) throws Throwable {
            Fingerprint fingerprint = (Fingerprint)invocation.getArguments()[0];
            fingerprint.setId(++fingerprintId);
            return fingerprint.getId();
        }

    }

    @Before
    public void setUp() throws SQLException {
        fingerprintData = mock(FingerprintData.class);
        fingerprintId = 0;
        when(fingerprintData.insert(any(Fingerprint.class))).thenAnswer(new FingerprintInsertAnswer());
        trackData = mock(TrackData.class);
        trackId = 0;
        when(trackData.insert(any(Track.class))).thenAnswer(new TrackInsertAnswer());
        when(trackData.insertMBID(anyInt(), anyString())).thenReturn(true);
        importer = new SubmissionImporter(fingerprintData, trackData);
    }

    private Submission createTestSubmission() {
        Submission submission = new Submission();
        submission.setId(1);
        submission.setBitrate(192);
        submission.setLength(130);
        submission.setData(new int[] { 1 });
        submission.setMBID("c54b2c05-0b59-48db-8923-2e3fa054a931");
        return submission;
    }

    @Test
    public void testEmptyDatabase() throws IOException, SQLException {
        Submission submission = createTestSubmission();
        importer.importSubmission(submission);
        ArgumentCaptor<Fingerprint> argument = ArgumentCaptor.forClass(Fingerprint.class);
        verify(fingerprintData).insert(argument.capture());
        assertEquals(192, argument.getValue().getBitrate());
        assertEquals(1, argument.getValue().getTrackId());
        assertArrayEquals(submission.getData(), argument.getValue().getData());
        assertEquals(130, argument.getValue().getLength());
        verify(trackData).insert(any(Track.class));
        verify(trackData).insertMBID(1, "c54b2c05-0b59-48db-8923-2e3fa054a931");
    }

    @Test
    public void testLowScoreMatch() throws IOException, SQLException {
        List<FingerprintSearchResult> searchResults = new ArrayList<FingerprintSearchResult>();
        searchResults.add(new FingerprintSearchResult(0.1, 1, 1));
        when(fingerprintData.search(anyInt(), any(int[].class), eq(1), anyDouble(), anyDouble(), eq(true))).thenReturn(searchResults);
        Submission submission = createTestSubmission();
        importer.importSubmission(submission);
        ArgumentCaptor<Fingerprint> argument = ArgumentCaptor.forClass(Fingerprint.class);
        verify(fingerprintData).insert(argument.capture());
        assertEquals(192, argument.getValue().getBitrate());
        assertEquals(1, argument.getValue().getTrackId());
        assertArrayEquals(submission.getData(), argument.getValue().getData());
        assertEquals(130, argument.getValue().getLength());
        verify(trackData).insert(any(Track.class));
        verify(trackData).insertMBID(1, "c54b2c05-0b59-48db-8923-2e3fa054a931");
    }

    @Test
    public void testGoodTrackScoreMatch() throws IOException, SQLException {
        List<FingerprintSearchResult> searchResults = new ArrayList<FingerprintSearchResult>();
        searchResults.add(new FingerprintSearchResult(0.8, 2, 3));
        when(fingerprintData.search(anyInt(), any(int[].class), eq(1), anyDouble(), anyDouble(), eq(true))).thenReturn(searchResults);
        Submission submission = createTestSubmission();
        importer.importSubmission(submission);
        ArgumentCaptor<Fingerprint> argument = ArgumentCaptor.forClass(Fingerprint.class);
        verify(fingerprintData).insert(argument.capture());
        assertEquals(192, argument.getValue().getBitrate());
        assertEquals(3, argument.getValue().getTrackId());
        assertArrayEquals(submission.getData(), argument.getValue().getData());
        assertEquals(130, argument.getValue().getLength());
        verify(trackData, never()).insert(any(Track.class));
        verify(trackData).insertMBID(3, "c54b2c05-0b59-48db-8923-2e3fa054a931");
    }

    @Test
    public void testGoodFingerprintScoreMatch() throws IOException, SQLException {
        List<FingerprintSearchResult> searchResults = new ArrayList<FingerprintSearchResult>();
        searchResults.add(new FingerprintSearchResult(0.98, 2, 3));
        when(fingerprintData.search(anyInt(), any(int[].class), eq(1), anyDouble(), anyDouble(), eq(true))).thenReturn(searchResults);
        Submission submission = createTestSubmission();
        importer.importSubmission(submission);
        verify(fingerprintData, never()).insert(any(Fingerprint.class));
        verify(trackData, never()).insert(any(Track.class));
        verify(trackData).insertMBID(3, "c54b2c05-0b59-48db-8923-2e3fa054a931");
    }

    @Test
    public void testImportSubmissions() throws IOException, SQLException, DataException {
        Transaction transaction = mock(Transaction.class);
        SubmissionData submissionData = mock(SubmissionData.class);
        importer.setSubmissionData(submissionData);
        importer.setTransaction(transaction);

        List<Submission> submissions = new ArrayList<Submission>();
        Submission submission = createTestSubmission();
        submissions.add(submission);
        when(submissionData.findUnhandled(anyInt(), eq(false))).thenReturn(submissions);

        importer.importSubmissions(10);

        verify(submissionData).findUnhandled(10, false);
        verify(submissionData).markAsHandled(1);

        ArgumentCaptor<Fingerprint> argument = ArgumentCaptor.forClass(Fingerprint.class);
        verify(fingerprintData).insert(argument.capture());
        assertEquals(192, argument.getValue().getBitrate());
        assertEquals(1, argument.getValue().getTrackId());
        assertArrayEquals(submission.getData(), argument.getValue().getData());
        assertEquals(130, argument.getValue().getLength());
        verify(trackData).insert(any(Track.class));
        verify(trackData).insertMBID(1, "c54b2c05-0b59-48db-8923-2e3fa054a931");
        verify(transaction).commit();
    }

    @Test
    public void testImportSubmissionsWithPUID() throws IOException, SQLException, DataException {
        Transaction transaction = mock(Transaction.class);
        SubmissionData submissionData = mock(SubmissionData.class);
        MusicBrainzPUIDData puidData = mock(MusicBrainzPUIDData.class);
        importer.setSubmissionData(submissionData);
        importer.setTransaction(transaction);
        importer.setMusicBrainzPUIDData(puidData);

        List<Submission> submissions = new ArrayList<Submission>();
        Submission submission = new Submission();
        submission.setId(2);
        submission.setBitrate(128);
        submission.setLength(60);
        submission.setData(new int[] { 2 });
        submission.setPUID("2114f36d-41c2-4db6-b765-a2d40891b780");
        submissions.add(submission);
        when(submissionData.findUnhandled(anyInt(), eq(false))).thenReturn(submissions);

        List<MusicBrainzTrack> tracks = new ArrayList<MusicBrainzTrack>();
        MusicBrainzTrack track = new MusicBrainzTrack();
        track.setMBID("c54b2c05-0b59-48db-8923-2e3fa054a931");
        tracks.add(track);
        MusicBrainzTrack track2 = new MusicBrainzTrack();
        track2.setMBID("86912df6-0d5f-4523-a66b-b5113def0b27");
        tracks.add(track2);
        when(puidData.findTracks(eq("2114f36d-41c2-4db6-b765-a2d40891b780"), anyInt(), anyInt())).thenReturn(tracks);

        importer.importSubmissions(10);

        verify(submissionData).findUnhandled(10, false);
        verify(submissionData).markAsHandled(2);

        ArgumentCaptor<Fingerprint> argument = ArgumentCaptor.forClass(Fingerprint.class);
        verify(fingerprintData).insert(argument.capture());
        assertEquals(128, argument.getValue().getBitrate());
        assertEquals(1, argument.getValue().getTrackId());
        assertArrayEquals(submission.getData(), argument.getValue().getData());
        assertEquals(60, argument.getValue().getLength());
        verify(trackData).insert(any(Track.class));
        verify(trackData).insertMBID(1, "c54b2c05-0b59-48db-8923-2e3fa054a931");
        verify(trackData).insertMBID(1, "86912df6-0d5f-4523-a66b-b5113def0b27");
        verify(transaction).commit();
    }

}
