import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

class UserModel {
  final String id;
  final String name;
  final String email;

  UserModel({required this.id, required this.name, required this.email});

  factory UserModel.fromJson(Map<String, dynamic> json) {
    return UserModel(
      id: json['id'],
      name: json['name'],
      email: json['email'],
    );
  }
}

class ProfileWidget extends StatelessWidget {
  final UserModel user;

  const ProfileWidget({Key? key, required this.user}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          children: [
            Text(user.name, style: Theme.of(context).textTheme.headlineSmall),
            Text(user.email),
          ],
        ),
      ),
    );
  }
}

mixin ValidationMixin {
  bool isValidEmail(String email) {
    return email.contains('@');
  }

  bool isValidName(String name) {
    return name.length >= 2;
  }
}
