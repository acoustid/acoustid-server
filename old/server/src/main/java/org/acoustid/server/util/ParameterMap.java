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

package org.acoustid.server.util;

import java.io.IOException;
import java.io.InputStream;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import java.util.zip.GZIPInputStream;
import javax.servlet.http.HttpServletRequest;
import org.acoustid.FingerprintUtils;
import org.acoustid.server.Chromaprint;
import org.acoustid.util.IncompatibleFingerprintVersion;
import org.apache.commons.lang.ArrayUtils;
import org.apache.http.NameValuePair;
import org.apache.http.client.utils.URLEncodedUtils;
import org.apache.http.entity.InputStreamEntity;

public class ParameterMap {

    private Map<String, String[]> map = null;

    public ParameterMap(Map<String, String[]> map) {
        this.map = map;
    }

    @Override
    public String toString() {
        StringBuilder builder = new StringBuilder();
        boolean first = true;
        for (String key : map.keySet()) {
            for (String value : map.get(key)) {
                if (!first) {
                    builder.append('\n');
                }
                builder.append(key).append("=").append(value);
                first = false;
            }
        }
        return builder.toString();
    }

    public boolean contains(String name) {
        return map.containsKey(name);
    }
    
    public String getString(String name) throws MissingParameterException {
        String[] values = getStringArray(name);
        if (values.length < 1)
            throw new MissingParameterException("Missing parameter '" + name + "'");
        return values[0];
    }

    public String[] getStringArray(String name) throws MissingParameterException {
        String[] values = map.get(name);
        if (values == null)
            throw new MissingParameterException("Missing parameter '" + name + "'");
        return values;
    }

    public int getInt(String name) throws ParameterFormatException, MissingParameterException {
        String stringValue = getString(name);
        try {
            return Integer.parseInt(stringValue);
        }
        catch (NumberFormatException ex) {
            throw new ParameterFormatException("Parameter '" + name + "' is not a valid number", ex);
        }
    }

    public double getDouble(String name) throws ParameterFormatException, MissingParameterException {
        String stringValue = getString(name);
        try {
            return Double.parseDouble(stringValue);
        }
        catch (NumberFormatException ex) {
            throw new ParameterFormatException("Parameter '" + name + "' is not a valid number", ex);
        }
    }

    public int getShort(String name) throws ParameterFormatException, MissingParameterException {
        return getShort(name, Short.MIN_VALUE);
    }

    public int getShort(String name, int minValue) throws ParameterFormatException, MissingParameterException {
        String stringValue = getString(name);
        try {
            short value = Short.parseShort(stringValue);
            if (value < minValue) {
                throw new ParameterFormatException("Parameter '" + name + "' must be greater than or equal to " + minValue);
            }
            return value;
        }
        catch (NumberFormatException ex) {
            throw new ParameterFormatException("Parameter '" + name + "' is not a valid number", ex);
        }
    }

    public String getUUIDString(String name) throws MissingParameterException, ParameterFormatException {
        String value = getString(name);
        try {
            UUID.fromString(value);
        }
        catch (IllegalArgumentException ex) {
            throw new ParameterFormatException("Parameter '" + name + "' is not a valid UUID", ex);
        }
        return value;
    }

    public String[] getUUIDStringArray(String name) throws MissingParameterException, ParameterFormatException {
        String[] values = getStringArray(name);
        try {
            for (int i = 0; i < values.length; i++) {
                UUID.fromString(values[i]);
            }
        }
        catch (IllegalArgumentException ex) {
            throw new ParameterFormatException("Parameter '" + name + "' is not a valid UUID", ex);
        }
        return values;
    }

    public int[] getFingerprint(String name) throws MissingParameterException, ParameterFormatException, IncompatibleFingerprintVersion {
        String value = getString(name);
        try {
            return FingerprintUtils.decodeFingerprint(value, Chromaprint.FINGERPRINT_VERSION);
        }
        catch (IllegalArgumentException ex) {
            throw new ParameterFormatException("Parameter '" + name + "' is not a valid fingerprint", ex);
        }
    }

    public static ParameterMap parseRequest(HttpServletRequest request) throws IOException {
        String contentEncoding = request.getHeader("Content-Encoding");
        if (contentEncoding != null) {
            contentEncoding = contentEncoding.toLowerCase();
        }
        String contentType = request.getContentType();
        Map<String, String[]> map;
        if ("gzip".equals(contentEncoding) && "application/x-www-form-urlencoded".equals(contentType)) {
            InputStream inputStream = new GZIPInputStream(request.getInputStream());
            InputStreamEntity entity = new InputStreamEntity(inputStream, -1);
            entity.setContentType(contentType);
            map = new HashMap<String, String[]>();
            for (NameValuePair param : URLEncodedUtils.parse(entity)) {
                String name = param.getName();
                String value = param.getValue();
                String[] values = map.get(name);
                if (values == null) {
                    values = new String[] { value };
                }
                else {
                    values = (String[])ArrayUtils.add(values, value);
                }
                map.put(name, values);
            }
        }
        else {
            map = request.getParameterMap();
        }
        return new ParameterMap(map);
    }

}
