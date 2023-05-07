# Copyright (C) 2012 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import datetime
import logging

from acoustid.api import errors
from acoustid.api.v2 import APIHandler, APIHandlerParams, check_app_api_key
from acoustid.data.account import insert_account
from acoustid.data.application import (
    find_applications_by_apikeys,
    insert_application,
    lookup_application_id,
    update_application_status,
)
from acoustid.data.stats import (
    find_application_lookup_stats_multi,
    update_lookup_stats,
    update_user_agent_stats,
)

logger = logging.getLogger(__name__)


class UpdateLookupStatsHandlerParams(APIHandlerParams):
    def parse(self, values, db):
        super(UpdateLookupStatsHandlerParams, self).parse(values, db)
        self.secret = values.get("secret")
        self.application_id = values.get("application_id", type=int)
        self.date = values.get("date")
        self.hour = values.get("hour", type=int)
        self.type = values.get("type")
        self.count = values.get("count", type=int)


class UpdateLookupStatsHandler(APIHandler):
    params_class = UpdateLookupStatsHandlerParams

    def _handle_internal(self, params):
        if self.ctx.config.cluster.role != "master":
            logger.warning(
                "Trying to call update_lookup_stats on %s server",
                self.ctx.config.cluster.role,
            )
            raise errors.NotAllowedError()
        if self.ctx.config.cluster.secret != params.secret:
            logger.warning("Invalid cluster secret")
            raise errors.NotAllowedError()
        app_db = self.ctx.db.get_app_db()
        update_lookup_stats(
            app_db,
            params.application_id,
            params.date,
            params.hour,
            params.type,
            params.count,
        )
        self.ctx.db.session.commit()
        return {}


class UpdateUserAgentStatsHandlerParams(APIHandlerParams):
    def parse(self, values, db):
        super(UpdateUserAgentStatsHandlerParams, self).parse(values, db)
        self.secret = values.get("secret")
        self.application_id = values.get("application_id", type=int)
        self.date = values.get("date")
        self.user_agent = values.get("user_agent")
        self.ip = values.get("ip")
        self.count = values.get("count", type=int)


class UpdateUserAgentStatsHandler(APIHandler):
    params_class = UpdateUserAgentStatsHandlerParams

    def _handle_internal(self, params):
        if self.ctx.config.cluster.role != "master":
            logger.warning(
                "Trying to call update_user_agent_stats on %s server",
                self.ctx.config.cluster.role,
            )
            raise errors.NotAllowedError()
        if self.ctx.config.cluster.secret != params.secret:
            logger.warning("Invalid cluster secret")
            raise errors.NotAllowedError()
        app_db = self.ctx.db.get_app_db()
        update_user_agent_stats(
            app_db,
            params.application_id,
            params.date,
            params.user_agent,
            params.ip,
            params.count,
        )
        self.ctx.db.session.commit()
        return {}


class LookupStatsHandlerParams(APIHandlerParams):
    def parse(self, values, db):
        super(LookupStatsHandlerParams, self).parse(values, db)
        self.secret = values.get("secret")
        apikeys = values.getlist("client")
        if not apikeys:
            raise errors.InvalidAPIKeyError()
        self.applications = find_applications_by_apikeys(db.get_app_db(), apikeys)
        if not self.applications:
            raise errors.InvalidAPIKeyError()
        self.from_date = values.get("from")
        if self.from_date is not None:
            self.from_date = datetime.datetime.strptime(
                self.from_date, "%Y-%m-%d"
            ).date()
        self.to_date = values.get("to")
        if self.to_date is not None:
            self.to_date = datetime.datetime.strptime(self.to_date, "%Y-%m-%d").date()
        self.days = values.get("days", type=int)


class LookupStatsHandler(APIHandler):
    params_class = LookupStatsHandlerParams

    def _handle_internal(self, params):
        if self.ctx.config.cluster.secret != params.secret:
            logger.warning("Invalid cluster secret")
            raise errors.NotAllowedError()
        application_ids = dict(
            (app["id"], app["apikey"]) for app in params.applications
        )
        kwargs = {}
        if params.from_date is not None:
            kwargs["from_date"] = params.from_date
        if params.to_date is not None:
            kwargs["to_date"] = params.to_date
        if params.days is not None:
            kwargs["days"] = params.days
        stats = find_application_lookup_stats_multi(
            self.ctx.db.get_app_db(), application_ids.keys(), **kwargs
        )
        for entry in stats:
            entry["date"] = entry["date"].strftime("%Y-%m-%d")
        return {"stats": stats}


class CreateAccountHandlerParams(APIHandlerParams):
    def parse(self, values, db):
        super(CreateAccountHandlerParams, self).parse(values, db)
        self.secret = values.get("secret")


class CreateAccountHandler(APIHandler):
    params_class = CreateAccountHandlerParams

    def _handle_internal(self, params):
        if self.ctx.config.cluster.secret != params.secret:
            logger.warning("Invalid cluster secret")
            raise errors.NotAllowedError()
        account_id, account_api_key = insert_account(
            self.ctx.db.get_app_db(),
            {
                "name": "External User",
                "anonymous": True,
            },
        )
        self.ctx.db.session.commit()
        return {"id": account_id, "api_key": account_api_key}


class CheckApplicationHandlerParams(APIHandlerParams):
    def parse(self, values, db):
        super(CreateApplicationHandlerParams, self).parse(values, db)
        self.secret = values.get("secret")
        self.api_key = values.get("api_key")


class CheckApplicationHandler(APIHandler):
    params_class = CheckApplicationHandlerParams

    def _handle_internal(self, params):
        if self.ctx.config.cluster.secret != params.secret:
            logger.warning("Invalid cluster secret")
            raise errors.NotAllowedError()
        application_id = check_app_api_key(
            self.ctx.config, self.ctx.db.get_app_db(), params.api_key
        )
        if not application_id:
            raise errors.InvalidAPIKeyError()
        return {"id": application_id}


class CreateApplicationHandlerParams(APIHandlerParams):
    def parse(self, values, db):
        super(CreateApplicationHandlerParams, self).parse(values, db)
        self.secret = values.get("secret")
        self.account_id = values.get("account_id", type=int)
        self.name = values.get("name")
        self.version = values.get("version")


class CreateApplicationHandler(APIHandler):
    params_class = CreateApplicationHandlerParams

    def _handle_internal(self, params):
        if self.ctx.config.cluster.secret != params.secret:
            logger.warning("Invalid cluster secret")
            raise errors.NotAllowedError()
        application_id, application_api_key = insert_application(
            self.ctx.db.get_app_db(),
            {
                "account_id": params.account_id,
                "name": params.name,
                "version": params.version,
            },
        )
        self.ctx.db.session.commit()
        return {"id": application_id, "api_key": application_api_key}


class UpdateApplicationStatusHandlerParams(APIHandlerParams):
    def parse(self, values, db):
        super(UpdateApplicationStatusHandlerParams, self).parse(values, db)
        self.secret = values.get("secret")
        self.account_id = values.get("account_id", type=int)
        self.application_id = values.get("application_id", type=int)
        if not lookup_application_id(
            db.get_app_db(), self.application_id, self.account_id
        ):
            raise errors.UnknownApplicationError()
        self.active = values.get("active", type=bool)


class UpdateApplicationStatusHandler(APIHandler):
    params_class = UpdateApplicationStatusHandlerParams

    def _handle_internal(self, params):
        if self.ctx.config.cluster.secret != params.secret:
            logger.warning("Invalid cluster secret")
            raise errors.NotAllowedError()
        update_application_status(
            self.ctx.db.get_app_db(), params.application_id, params.active
        )
        self.ctx.db.session.commit()
        return {"id": params.application_id, "active": params.active}
