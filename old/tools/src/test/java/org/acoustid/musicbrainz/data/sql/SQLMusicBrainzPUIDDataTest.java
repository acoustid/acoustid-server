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

package org.acoustid.musicbrainz.data.sql;

import org.acoustid.test.DatabaseTestCase;
import org.junit.Test;
import static org.junit.Assert.*;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.List;
import org.acoustid.musicbrainz.MusicBrainzTrack;

public class SQLMusicBrainzPUIDDataTest extends DatabaseTestCase {

    @Test
    public void testFindTracks() throws SQLException, ClassNotFoundException {
        Connection connection = setUpDatabase();
        runSql(connection, "TRUNCATE musicbrainz.artist CASCADE");
        runSql(connection, "TRUNCATE musicbrainz.track CASCADE");
        runSql(connection, "TRUNCATE musicbrainz.puid CASCADE");
        runSql(connection, "TRUNCATE musicbrainz.puidjoin CASCADE");
        runSql(connection, "INSERT INTO musicbrainz.artist (id, gid, name, sortname, page)"
                + "VALUES (1, 'de8ebf7e-9461-4feb-8d67-afca02855055', 'Artist 1', 'Artist 1', 0)");
        runSql(connection, "INSERT INTO musicbrainz.track (id, gid, name, length, artist)"
                + "VALUES (1, '127a7c27-a36e-4b88-9831-429cd2c03cbd', 'Track 1', 223000, 1),"
                + "       (2, '2212f29e-d546-406b-a1c1-4c92f3f28e77', 'Track 2', 226000, 1),"
                + "       (3, 'a3aac370-a06a-4ea0-956d-dc171df6eb13', 'Track 3', 228000, 1)");
        runSql(connection, "INSERT INTO musicbrainz.puid (id, puid, version)"
                + "VALUES (1, '682426e4-bc5b-4996-a5ee-efba782fc463', 0)");
        runSql(connection, "INSERT INTO musicbrainz.puidjoin (puid, track)"
                + "VALUES (1, 1), (1, 3)");
        SQLMusicBrainzPUIDData puidData = new SQLMusicBrainzPUIDData();
        puidData.setConnection(connection);
        List<MusicBrainzTrack> tracks = puidData.findTracks("682426e4-bc5b-4996-a5ee-efba782fc463", 224, 229);
        assertEquals(1, tracks.size());
        assertEquals("a3aac370-a06a-4ea0-956d-dc171df6eb13", tracks.get(0).getMBID());
        tracks = puidData.findTracks("682426e4-bc5b-4996-a5ee-efba782fc463", 223, 229);
        assertEquals(2, tracks.size());
        assertEquals("127a7c27-a36e-4b88-9831-429cd2c03cbd", tracks.get(0).getMBID());
        assertEquals("a3aac370-a06a-4ea0-956d-dc171df6eb13", tracks.get(1).getMBID());
    }


}
