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

import java.sql.SQLException;
import java.util.List;
import org.acoustid.FingerprintSearchResult;
import org.acoustid.data.FingerprintData;

abstract public class AbstractFingerprintData extends Data implements FingerprintData {

    private static final double MIN_SCORE = 0.01;

    public AbstractFingerprintData() {
    }

    @Override
    public List<FingerprintSearchResult> search(int length, int[] data) throws SQLException {
        return search(length, data, 0, MIN_SCORE);
    }

    @Override
    public List<FingerprintSearchResult> search(int length, int[] data, int limit) throws SQLException {
        return search(length, data, limit, MIN_SCORE);
    }

    @Override
    public List<FingerprintSearchResult> search(int length, int[] data, int limit, double minScore) throws SQLException {
        return search(length, data, limit, minScore, 2.0);
    }

    @Override
    public List<FingerprintSearchResult> search(int length, int[] data, int limit, double minScore, double idealScore) throws SQLException {
        return search(length, data, limit, minScore, idealScore, false);
    }

}
