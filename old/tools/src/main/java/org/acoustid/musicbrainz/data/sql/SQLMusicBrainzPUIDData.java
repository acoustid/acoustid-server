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

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import org.acoustid.data.sql.Data;
import org.acoustid.musicbrainz.MusicBrainzTrack;
import org.acoustid.musicbrainz.data.MusicBrainzPUIDData;

public class SQLMusicBrainzPUIDData extends Data implements MusicBrainzPUIDData {

    @Override
    public List<MusicBrainzTrack> findTracks(String puid, int minLength, int maxLength) throws SQLException {
        String sql =
                "SELECT t.gid "
                + "FROM musicbrainz.track t "
                + "JOIN musicbrainz.puidjoin pj ON pj.track=t.id "
                + "JOIN musicbrainz.puid p ON pj.puid=p.id "
                + "WHERE p.puid = ?::uuid AND t.length BETWEEN ? AND ? "
                + "ORDER BY t.id";
        PreparedStatement statement = getConnection().prepareStatement(sql);
        statement.setString(1, puid);
        statement.setInt(2, minLength * 1000);
        statement.setInt(3, maxLength * 1000);
        ResultSet rs = statement.executeQuery();
        List<MusicBrainzTrack> results = new ArrayList<MusicBrainzTrack>();
        while (rs.next()) {
            MusicBrainzTrack result = new MusicBrainzTrack();
            result.setMBID(rs.getString("gid"));
            results.add(result);
        }
        statement.close();
        return results;
    }

}
