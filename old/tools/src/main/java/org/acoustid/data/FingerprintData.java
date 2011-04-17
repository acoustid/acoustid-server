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

import java.sql.SQLException;
import java.util.List;
import org.acoustid.Fingerprint;
import org.acoustid.FingerprintSearchResult;

public interface FingerprintData {

    /**
     * Insert a new fingerprint into the database
     *
     * This method also sets the "id" attribute of the fingerprint object.
     *
     * @param fingerprint fingerprint object to be inserted
     * @return ID of the inserted fingerprint
     * @throws SQLException
     */
    int insert(Fingerprint fingerprint) throws SQLException;

    /**
     * Search for the specified fingerprint and return matching entries.
     *
     * @param length
     * @param data
     * @return list of matching results
     * @throws SQLException 
     */
    List<FingerprintSearchResult> search(int length, int[] data) throws SQLException;

    /**
     * Search for the specified fingerprint and return matching entries.
     *
     * @param length
     * @param data
     * @param limit
     * @return list of matching results
     * @throws SQLException
     */
    List<FingerprintSearchResult> search(int length, int[] data, int limit) throws SQLException;

    /**
     * Search for the specified fingerprint and return matching entries.
     *
     * @param length
     * @param data
     * @param limit maximum number of record returned (0 means no limit)
     * @param minScore only results with higher score are returned
     * @return list of matching results
     * @throws SQLException
     */
    List<FingerprintSearchResult> search(int length, int[] data, int limit, double minScore) throws SQLException;

    /**
     * Search for the specified fingerprint and return matching entries.
     *
     * @param length
     * @param data
     * @param limit maximum number of record returned (0 means no limit)
     * @param minScore only results with higher score are returned
     * @param idealScore stop searching are finding a result with higher score
     * @return list of matching results
     * @throws SQLException
     */
    List<FingerprintSearchResult> search(int length, int[] data, int limit, double minScore, double idealScore) throws SQLException;

    List<FingerprintSearchResult> search(int length, int[] data, int limit, double minScore, double idealScore, boolean fast) throws SQLException;
}
