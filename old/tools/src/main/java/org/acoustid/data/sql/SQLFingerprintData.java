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
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import org.acoustid.Fingerprint;

import org.acoustid.FingerprintSearchResult;
import org.acoustid.data.FingerprintData;

public class SQLFingerprintData extends AbstractFingerprintData implements FingerprintData {

    private static final int MAX_LENGTH_DIFF = 7;

    private static final String SEARCH_SQL =
        "SELECT id, track_id, score FROM ("
        + "SELECT id, track_id, acoustid_compare(fingerprint, query) AS score "
        + "FROM fingerprint, (SELECT ?::int4[] AS query) q "
        + "WHERE"
        + "    length BETWEEN ? AND ? AND ("
        + "        (? >= 34 AND extract_fp_query(query) && extract_fp_query(fingerprint)) OR "
        + "        (? <= 50 AND extract_short_fp_query(query) && extract_short_fp_query(fingerprint)) "
        + "    ) "
        + ") f WHERE score > ? ORDER BY score DESC";

    private static final String PART_SEARCH_SQL =
        "SELECT id, track_id, score FROM ("
        + "SELECT id, track_id, acoustid_compare(fingerprint, query) AS score "
        + "FROM fingerprint, (SELECT ?::int4[] AS query) q "
        + "WHERE"
        + "    length BETWEEN ? AND ? AND ("
        + "        (? >= 34 AND subarray(extract_fp_query(query), ?, ?) && extract_fp_query(fingerprint)) OR "
        + "        (? <= 50 AND subarray(extract_short_fp_query(query), ?, ?) && extract_short_fp_query(fingerprint)) "
        + "    ) "
        + ") f WHERE score > ? ORDER BY score DESC";

    @Override
    public List<FingerprintSearchResult> search(int length, int[] data, int limit, double minScore, double idealScore, boolean fast) throws SQLException {
        String encodedData = DataUtils.encodeIntArray(data);
        List<FingerprintSearchResult> results = new ArrayList<FingerprintSearchResult>();
        if (idealScore > 1.0) {
            fullSearch(results, length, encodedData, limit, minScore);
            return results;
        }
        double bestScore = partSearch(results, 100, 20, length, encodedData, limit, minScore);
        if (fast || bestScore >= idealScore) {
            return results;
        }
        partSearch(results, 1, 100, length, encodedData, limit, minScore);
        Collections.sort(results, new Comparator<FingerprintSearchResult>() {
            @Override
            public int compare(FingerprintSearchResult o1, FingerprintSearchResult o2) {
                return Double.compare(o1.getScore(), o2.getScore());
            }
        });
        return results;
    }

    private double partSearch(List<FingerprintSearchResult> results, int partStart, int partLength, int length, String encodedData, int limit, double minScore) throws SQLException {
        String sql = PART_SEARCH_SQL;
        if (limit > 0) {
            sql += " LIMIT ?";
        }
        PreparedStatement statement = getConnection().prepareStatement(sql);
        statement.setString(1, encodedData);
        statement.setInt(2, length - MAX_LENGTH_DIFF);
        statement.setInt(3, length + MAX_LENGTH_DIFF);
        statement.setInt(4, length);
        statement.setInt(5, partStart);
        statement.setInt(6, partLength);
        statement.setInt(7, length);
        statement.setInt(8, partStart);
        statement.setInt(9, partLength);
        statement.setDouble(10, minScore);
        if (limit > 0) {
            statement.setInt(11, limit);
        }
        double bestScore = 0.0;
        ResultSet rs = statement.executeQuery();
        while (rs.next()) {
            FingerprintSearchResult result = new FingerprintSearchResult();
            double score = rs.getDouble("score");
            if (score > bestScore) {
                bestScore = score;
            }
            result.setScore(score);
            result.setFingerprintId(rs.getInt("id"));
            result.setTrackId(rs.getInt("track_id"));
            results.add(result);
        }
        statement.close();
        return bestScore;
    }

    private double fullSearch(List<FingerprintSearchResult> results,int length, String encodedData, int limit, double minScore) throws SQLException {
        String sql = SEARCH_SQL;
        if (limit > 0) {
            sql += " LIMIT ?";
        }
        PreparedStatement statement = getConnection().prepareStatement(sql);
        statement.setString(1, encodedData);
        statement.setInt(2, length - MAX_LENGTH_DIFF);
        statement.setInt(3, length + MAX_LENGTH_DIFF);
        statement.setInt(4, length);
        statement.setInt(5, length);
        statement.setDouble(6, minScore);
        if (limit > 0) {
            statement.setInt(7, limit);
        }
        double bestScore = 0.0;
        ResultSet rs = statement.executeQuery();
        while (rs.next()) {
            FingerprintSearchResult result = new FingerprintSearchResult();
            double score = rs.getDouble("score");
            if (score > bestScore) {
                bestScore = score;
            }
            result.setScore(score);
            result.setFingerprintId(rs.getInt("id"));
            result.setTrackId(rs.getInt("track_id"));
            results.add(result);
        }
        statement.close();
        return bestScore;
    }

    private static final String INSERT_SQL =
        "INSERT INTO fingerprint (fingerprint, length, track_id, source_id, format_id, bitrate) "
        + "VALUES (?::int4[], ?, ?, ?, ?, ?) RETURNING id";

    @Override
    public int insert(Fingerprint fingerprint) throws SQLException {
        PreparedStatement statement = getConnection().prepareStatement(INSERT_SQL);
        statement.setString(1, DataUtils.encodeIntArray(fingerprint.getData()));
        statement.setInt(2, fingerprint.getLength());
        statement.setInt(3, fingerprint.getTrackId());
        statement.setInt(4, fingerprint.getSourceId());
        if (fingerprint.getFormatId() > 0) {
            statement.setInt(5, fingerprint.getFormatId());
        }
        else {
            statement.setNull(5, Types.INTEGER);
        }
        if (fingerprint.getBitrate() > 0) {
            statement.setInt(6, fingerprint.getBitrate());
        }
        else {
            statement.setNull(6, Types.INTEGER);
        }
        ResultSet rs = statement.executeQuery();
        rs.next();
        int id = rs.getInt(1);
        fingerprint.setId(id);
        statement.close();
        return id;
    }

}
