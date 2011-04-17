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

import com.google.common.base.CharMatcher;
import com.google.common.base.Splitter;
import java.util.Iterator;

public class DataUtils {

    /**
     * Encodes Java int array into a PostgreSQL-formatted array string.
     *
     * @param str
     * @return
     */
    public static String encodeIntArray(int[] data) {
        return encodeIntArray(data, '{', '}');
    }

    public static String encodeIntArray(int[] data, char leftParent, char rightParen) {
        StringBuilder builder = new StringBuilder(data.length * 6);
        builder.append(leftParent);
        int length = data.length - 1;
        for (int i = 0; i < length; i++) {
            builder.append(data[i]);
            builder.append(',');
        }
        if (length >= 0) {
            builder.append(data[length]);
        }
        builder.append(rightParen);
        return builder.toString();
    }

    /**
     * Decodes PostgreSQL-formatted array string into a Java int array.
     *
     * @param str
     * @return
     */
    public static int[] decodeIntArray(String str) {
        int length = str.length();
        if (str.charAt(0) != '{' || str.charAt(length - 1) != '}')
            throw new IllegalArgumentException("Invalid PostgreSQL array representation");
        return decodeIntArray(str.subSequence(1, length - 1), ',');
    }

    private static int[] decodeIntArray(CharSequence str, char sep) {
        int length = 1 + CharMatcher.is(sep).countIn(str);
        int[] result = new int[length];
        Iterator<String> iter = Splitter.on(sep).split(str).iterator();
        int i = 0;
        while (iter.hasNext()) {
            long longValue = Long.parseLong(iter.next(), 10);
            result[i++] = (longValue <= Integer.MAX_VALUE)
                ? (int)(longValue)
                : (int)(longValue & Integer.MAX_VALUE - Integer.MAX_VALUE - 1);
        }
        return result;
    }

}
