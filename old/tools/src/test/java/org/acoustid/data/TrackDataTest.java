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

package org.acoustid.data;

import org.acoustid.data.sql.SQLTrackData;
import org.acoustid.test.DatabaseTestCase;
import org.junit.Test;
import static org.junit.Assert.*;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import org.acoustid.Track;

public class TrackDataTest extends DatabaseTestCase {

    @Test
    public void testInsert() throws SQLException, ClassNotFoundException {
        Connection connection = setUpDatabase();
        SQLTrackData trackData = new SQLTrackData();
        trackData.setConnection(connection);
        Track track = new Track();
		trackData.insert(track);
        assertEquals(1, track.getId());
        Track track2 = new Track();
		trackData.insert(track2);
        assertEquals(2, track2.getId());
    }

    @Test
    public void testInsertMBID() throws SQLException, ClassNotFoundException {
        Connection connection = setUpDatabase();
        runSql(connection, "INSERT INTO track (id) VALUES (nextval('track_id_seq'))");
        SQLTrackData trackData = new SQLTrackData();
        trackData.setConnection(connection);
		// Inserted
		assertTrue(trackData.insertMBID(1, "7ce8a976-f46b-443a-ab62-f728b8ca0d73"));
		// Not inserted, already there
		assertFalse(trackData.insertMBID(1, "7ce8a976-f46b-443a-ab62-f728b8ca0d73"));
    }

    @Test
    public void testLoadMBIDs() throws SQLException, ClassNotFoundException {
        Connection connection = setUpDatabase();
        runSql(connection, "INSERT INTO track (id) VALUES (nextval('track_id_seq'))");
        runSql(connection, "INSERT INTO track_mbid (track_id, mbid) VALUES (1, '7ce8a976-f46b-443a-ab62-f728b8ca0d73')");
        SQLTrackData trackData = new SQLTrackData();
        trackData.setConnection(connection);
        List<Track> tracks = new ArrayList<Track>();
        tracks.add(new Track(1));
        trackData.loadMBIDs(tracks);
		assertEquals(1, tracks.get(0).getMBIDs().size());
		assertEquals("7ce8a976-f46b-443a-ab62-f728b8ca0d73", tracks.get(0).getMBIDs().get(0));
        List<Track> tracks2 = new ArrayList<Track>();
        trackData.loadMBIDs(tracks2);
    }

}
