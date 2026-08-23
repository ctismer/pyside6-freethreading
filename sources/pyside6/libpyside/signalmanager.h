// Copyright (C) 2016 The Qt Company Ltd.
// SPDX-License-Identifier: LicenseRef-Qt-Commercial OR LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only
// Qt-Security score:significant reason:default

#ifndef SIGNALMANAGER_H
#define SIGNALMANAGER_H

#include "pysidemacros.h"

#include <sbkpython.h>

#include <QtCore/qmetaobject.h>

#include <optional>

namespace PySide::SignalManager
{
    using QmlMetaCallErrorHandler = std::optional<int>(*)(QObject *object);

    PYSIDE_API void setQmlMetaCallErrorHandler(QmlMetaCallErrorHandler handler);

    PYSIDE_API bool emitSignal(QObject *source, const char* signal, PyObject *args);
    PYSIDE_API bool emitSignal(QObject *source, int signalIndex, PyObject *args);
    PYSIDE_API int qt_metacall(QObject *object, QMetaObject::Call call, int id, void **args);

    // Used to register a new signal/slot on QMetaobject of source.
    PYSIDE_API bool registerMetaMethod(QObject *source, const char *signature,
                                       QMetaMethod::MethodType type);

    // used to discovery metaobject
    PYSIDE_API const QMetaObject* retrieveMetaObject(PyObject *self);

#ifdef Py_GIL_DISABLED
    /// The same from the C++ pointer, for the generated metaObject().
    /// nullptr when there is no Python wrapper. Takes a void pointer, not a
    /// QObject one: it is a wrapper map key, and under multiple inheritance
    /// the QObject subobject is not at the registered address.
    PYSIDE_API const QMetaObject *retrieveMetaObjectForCppObject(const void *cppSelf);
#endif

} // namespace PySide::SignalManager

#endif // SIGNALMANAGER_H
