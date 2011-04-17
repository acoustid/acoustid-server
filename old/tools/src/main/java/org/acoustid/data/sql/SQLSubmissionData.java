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

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;
import java.util.ArrayList;
import java.util.List;
import org.acoustid.Submission;
import org.acoustid.data.SubmissionData;

public class SQLSubmissionData extends Data implements SubmissionData {

    private static final String SELECT_UNHANDLED_SQL =
        "SELECT id, fingerprint, length, mbid, format_id, bitrate, source_id, puid "
        + "FROM submission WHERE handled = false ORDER BY id LIMIT ?";

    private static final String SELECT_UNHANDLED_NEW_SQL =
        "SELECT s.id, s.fingerprint, s.length, s.mbid, s.format_id, s.bitrate, s.source_id, s.puid "
        + "FROM submission s LEFT JOIN track_mbid t ON s.mbid=t.mbid "
        + "WHERE handled = false AND t.mbid IS NULL "
        + "ORDER BY id LIMIT ?";

    private static final String INSERT_SQL =
        "INSERT INTO submission (fingerprint, length, source_id, mbid, format_id, bitrate, puid) "
        + "VALUES (?::int4[], ?, ?, ?::uuid, ?, ?, ?::uuid) RETURNING id";

    private static final String DELETE_SQL =
        "DELETE FROM submission WHERE id = ?";

    private Submission createSubmission(ResultSet rs) throws SQLException {
        Submission submission = new Submission();
        submission.setId(rs.getInt("id"));
        submission.setLength(rs.getInt("length"));
        submission.setData(DataUtils.decodeIntArray(rs.getString("fingerprint")));
        submission.setMBID(rs.getString("mbid"));
        submission.setFormatId(rs.getInt("format_id"));
        submission.setSourceId(rs.getInt("source_id"));
        submission.setBitrate(rs.getInt("bitrate"));
        submission.setPUID(rs.getString("puid"));
        return submission;
    }

    private List<Submission> findUnhandled(String sql, int limit, boolean lock) throws SQLException {
        if (lock) {
            sql += " FOR UPDATE NOWAIT";
        }
        PreparedStatement statement = getConnection().prepareStatement(sql);
        statement.setInt(1, limit);
        ResultSet rs = statement.executeQuery();
        List<Submission> results = new ArrayList<Submission>();
        while (rs.next()) {
            results.add(createSubmission(rs));
        }
        statement.close();
        return results;
    }

    public List<Submission> findUnhandled(int limit) throws SQLException {
        return findUnhandled(limit, false);
    }

    @Override
    public List<Submission> findUnhandled(int limit, boolean lock) throws SQLException {
        List<Submission> results = findUnhandled(SELECT_UNHANDLED_NEW_SQL, limit, lock);
        if (results.isEmpty()) {
            results = findUnhandled(SELECT_UNHANDLED_SQL, limit, lock);
        }
        return results;
    }

    @Override
    public int insert(Submission submission) throws SQLException {
        PreparedStatement statement = getConnection().prepareStatement(INSERT_SQL);
        statement.setString(1, DataUtils.encodeIntArray(submission.getData()));
        statement.setInt(2, submission.getLength());
        statement.setInt(3, submission.getSourceId());
        statement.setString(4, submission.getMBID());
        if (submission.getFormatId() > 0) {
            statement.setInt(5, submission.getFormatId());
        }
        else {
            statement.setNull(5, Types.INTEGER);
        }
        if (submission.getBitrate() > 0) {
            statement.setInt(6, submission.getBitrate());
        }
        else {
            statement.setNull(6, Types.INTEGER);
        }
        statement.setString(7, submission.getPUID());
        ResultSet rs = statement.executeQuery();
        rs.next();
        int id = rs.getInt(1);
        submission.setId(id);
        statement.close();
        return id;
    }

    @Override
    public void delete(int id) throws SQLException {
        PreparedStatement statement = getConnection().prepareStatement(DELETE_SQL);
        statement.setInt(1, id);
        statement.execute();
        statement.close();
    }

    @Override
    public void markAsHandled(int id) throws SQLException {
        String sql = "UPDATE submission SET handled = true WHERE id = ?";
        PreparedStatement statement = getConnection().prepareStatement(sql);
        statement.setInt(1, id);
        statement.execute();
        statement.close();
    }

}
