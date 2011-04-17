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

package org.acoustid.data.sql;

import com.google.inject.Inject;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.acoustid.Fingerprint;

import org.acoustid.Track;
import org.acoustid.data.TrackData;
import org.apache.commons.lang.ArrayUtils;

public class SQLTrackData extends Data implements TrackData {

    @Override
    public int insert(Track track) throws SQLException {
        String sql = "INSERT INTO track (id) VALUES (nextval('track_id_seq')) RETURNING id";
        PreparedStatement statement = getConnection().prepareStatement(sql);
        ResultSet rs = statement.executeQuery();
        rs.next();
        int id = rs.getInt(1);
        track.setId(id);
        statement.close();
        return id;
    }

    @Override
    public boolean insertMBID(int trackId, String mbid) throws SQLException {
        String selectSql = "SELECT 1 FROM track_mbid WHERE track_id=? AND mbid=?::uuid";
        PreparedStatement statement = getConnection().prepareStatement(selectSql);
        statement.setInt(1, trackId);
        statement.setString(2, mbid);
        ResultSet rs = statement.executeQuery();
        if (!rs.next()) {
            statement.close();
            String insertSql = "INSERT INTO track_mbid (track_id, mbid) VALUES (?, ?::uuid)";
            PreparedStatement insertStatement = getConnection().prepareStatement(insertSql);
            insertStatement.setInt(1, trackId);
            insertStatement.setString(2, mbid);
            insertStatement.execute();
            insertStatement.close();
            return true;
        }
        statement.close();
        return false;
    }

    @Override
    public void loadMBIDs(List<Track> tracks) throws SQLException {
        if (tracks.isEmpty()) {
            return;
        }
        Map<Integer, Track> trackMap = new HashMap<Integer, Track>();
        for (Track track: tracks) {
            trackMap.put(track.getId(), track);
        }
        int[] trackIds = ArrayUtils.toPrimitive(trackMap.keySet().toArray(new Integer[0]));
        String sql = "SELECT track_id, mbid FROM track_mbid WHERE track_id IN "
                     + DataUtils.encodeIntArray(trackIds, '(', ')')
                     + " ORDER BY track_id, mbid";
        PreparedStatement statement = getConnection().prepareStatement(sql);
        ResultSet rs = statement.executeQuery();
        while (rs.next()) {
            int trackId = rs.getInt("track_id");
            Track track = trackMap.get(trackId);
            if (track.getMBIDs() == null) {
                track.setMBIDs(new ArrayList<String>(1));
            }
            track.getMBIDs().add(rs.getString("mbid"));
        }
        statement.close();
    }

}
